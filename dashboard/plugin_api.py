"""Claude Code Desktop parity - backend half.

Runs inside the Hermes gateway process (dashboard plugin API namespace
``/api/plugins/claude-code-parity/``).

What it does
------------
* Builds the model picker from Hermes' OWN ``build_model_options_payload``
  inventory (every authenticated provider) — no provider is hardcoded.
* Starts the LOCAL Claude Code CLI (``-p --output-format stream-json``) for each
  turn, with a per-session settings.json generated from the plugin's full
  settings schema (CLI flags + Claude Code settings.json keys).
* Claude Code speaks Anthropic ``/v1/messages``; almost every Hermes provider
  speaks OpenAI ``/chat/completions``. A per-turn, loopback-only protocol bridge
  translates in both directions (SSE + tools + images).
* Exposes attachments (image/video/file), a one-click Claude Code upgrade,
  a persistent settings store, and an honest CLI capability matrix.

The bridge binds to 127.0.0.1 on an ephemeral port, lives only for one turn,
and is shut down when the CLI exits. No credentials leave the gateway process.
"""

from __future__ import annotations

import base64
import json
from collections import deque
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from urllib.parse import unquote

router = APIRouter()

PLUGIN_ID = "claude-code-parity"
NPM_PKG = "@anthropic-ai/claude-code"


def _native_under(folder: Path) -> Path | None:
    """The real Claude Code binary inside an npm install rooted at *folder*."""
    for rel in (("node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"),
                ("node_modules", "@anthropic-ai", "claude-code", "cli.js")):
        candidate = folder.joinpath(*rel)
        if candidate.is_file():
            return candidate
    return None


def _find_claude() -> Path:
    """Locate the Claude Code entry point on THIS machine — nothing baked in.

    Order: an explicit override (``CCP_CLAUDE_BIN`` / ``CLAUDE_BIN``), then the
    native binary inside an npm install found on ``PATH`` or at the npm global
    root, then the per-user locations Claude Code installs itself into. A bare
    name is the last resort, so the diagnostics can say what is missing.

    The npm shim (``claude.cmd``, a few hundred bytes that re-execs the real
    binary) is deliberately not returned: this plugin drives the process
    directly, and a shim would be reported as a corrupt install.
    """
    for var in ("CCP_CLAUDE_BIN", "CLAUDE_BIN"):
        raw = os.environ.get(var, "").strip()
        if raw and Path(raw).exists():
            return Path(raw)

    home = Path.home()
    dirs: list[Path] = [Path(p) for p in (os.environ.get("PATH") or "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            out = subprocess.run([npm, "root", "-g"], capture_output=True,
                                 text=True, timeout=20)
            if out.stdout.strip():
                dirs.append(Path(out.stdout.strip()))
        except Exception:
            pass
    dirs += [home / ".claude" / "local", home / ".local" / "bin",
             home / "AppData" / "Roaming" / "npm", home / ".npm-global" / "bin"]

    seen: set[str] = set()
    for folder in dirs:
        key = str(folder).lower()
        if key in seen:
            continue
        seen.add(key)
        native = _native_under(folder)
        if native:
            return native
        for name in ("claude.exe", "claude"):
            candidate = folder / name
            if candidate.is_file():
                return candidate
    for name in ("claude.cmd", "claude.ps1"):
        hit = shutil.which(name)
        if hit:
            native = _native_under(Path(hit).parent)
            if native:
                return native
    return Path("claude")


CLAUDE_EXE = _find_claude()
DEFAULT_CWD = str(Path.home())

ALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    "Agent", "NotebookEdit", "TodoWrite", "TaskOutput", "KillShell",
]

# In-plugin approval: Claude Code --permission-prompt-tool MCP bridge.
# Verified against local claude.exe 2.1.322: with --permission-prompts host the
# CLI calls mcp__cc_approval__approve with {tool_name,input,tool_use_id} and
# reads a single MCP text block containing a JSON permission result.
APPROVAL_TOOL = "mcp__cc_approval__approve"
MCP_SCRIPT = Path(__file__).with_name("approval_mcp.py")
DEFAULT_ASK_TOOLS = [
    "Bash", "PowerShell", "Write", "Edit", "NotebookEdit",
    "WebFetch", "WebSearch", "Agent", "Task", "KillShell",
]

_JOBS: dict[str, dict[str, Any]] = {}
_PENDING: dict[str, dict[str, Any]] = {}
_APPROVAL_LOCK = threading.Lock()
_JOBS_LOCK = threading.Lock()
_CATALOG_CACHE: dict[str, Any] = {"at": 0.0, "groups": []}
_PROBE_CACHE: dict[str, tuple[float, dict]] = {}
_CLAUDE_VERSION: str | None = None
_RUNTIME_LOCK = threading.Lock()
_SETTINGS_LOCK = threading.Lock()
_UPGRADE_LOCK = threading.Lock()
_CLI_HELP_CACHE: dict[str, Any] = {}

_UPGRADE: dict[str, Any] = {
    "running": False, "started": 0.0, "log": [], "exit": None,
    "before": "", "after": "", "latest": "", "method": "", "error": "",
}


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def _home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    if raw and Path(raw).is_dir():
        return Path(raw)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config.yaml").is_file() and (parent / "hermes-agent").is_dir():
            return parent
    return Path.home() / ".hermes"


HOME = _home()
HERMES_SRC = HOME / "hermes-agent"


def _root_home() -> Path:
    """The installation root, even when this API runs inside a served profile.

    Dashboard plugin APIs of a secondary profile run in that profile's plugin host
    with ``HERMES_HOME`` pointing at ``<root>/profiles/<name>``. Model discovery and
    credentials, however, must come from the installation root: a profile config is
    often a trimmed override (for example only a local Qwen provider), and listing
    just those models would hide every model the user authenticated at the root.
    """
    if HOME.parent.name.lower() == "profiles":
        return HOME.parent.parent
    return HOME


ROOT_HOME = _root_home()
RUNTIME = HOME / "desktop-plugins" / PLUGIN_ID / ".runtime"
UPLOADS = RUNTIME / "uploads"
APPROVALS = RUNTIME / "approvals"
SETTINGS_FILE = RUNTIME / "plugin-settings.json"
_CATALOG_ENV_LOCK = threading.Lock()


def _install_dir() -> Path:
    """Find the npm project root that DEPENDS on @anthropic-ai/claude-code.

    The package's own package.json also mentions "claude-code" (its `name`),
    so match on `dependencies` instead of a substring search — otherwise the
    upgrade command would run inside node_modules/@anthropic-ai/claude-code.
    """
    for parent in CLAUDE_EXE.parents:
        pj = parent / "package.json"
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
            deps = data.get("dependencies") or {}
            dev = data.get("devDependencies") or {}
            if "@anthropic-ai/claude-code" in deps or "@anthropic-ai/claude-code" in dev:
                return parent
        except Exception:
            pass
    return CLAUDE_EXE.parent if CLAUDE_EXE.parent.is_dir() else Path.home()


INSTALL_DIR = _install_dir()


def _ensure_hermes_path() -> None:
    text = str(HERMES_SRC)
    if HERMES_SRC.is_dir() and text not in sys.path:
        sys.path.insert(0, text)


def _config() -> dict:
    try:
        import yaml
        return yaml.safe_load((ROOT_HOME / "config.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    try:
        _ensure_hermes_path()
        from hermes_cli.config import load_config
        return load_config() or {}
    except Exception:
        return {}


def _dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in (ROOT_HOME / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _auth() -> dict:
    try:
        return json.loads((ROOT_HOME / "auth.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Full settings schema: CLI flags + settings.json keys + plugin UI options
# --------------------------------------------------------------------------

G_MODEL = "模型与推理"
G_PERM = "权限与安全"
G_PROMPT = "提示词与输出"
G_SESSION = "会话与扩展"
G_UI = "外观与界面"
G_RUN = "运行参数"

_PERMISSION_MODES = ["acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"]
_EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]


# --------------------------------------------------------------------------
# Backend display-text catalogue (Chinese is the source language; English here)
# --------------------------------------------------------------------------
# The settings schema, the capability matrix and every runtime diagnostic are
# authored in Chinese because that is this project's source language. The UI
# can be switched to English, and half of what the user reads is produced here,
# not in the JSX — so the API translates its own strings on the way out.
#
# Two tables, for two different shapes:
#   *_EN*   whole strings:                 "模型与推理"  -> "Models & reasoning"
#   *_FRAG* fragments that get concatenated with live values, e.g.
#           "文件只有 " + "160" + " 字节，已损坏"  ->  "File is only 160 bytes — corrupted"
# Fragments are matched longest-first so "Claude Code 安装不可用（" wins over
# "Claude Code 不可用（". `_tr` returns the input untouched unless it contains
# CJK, so model output, tool output and user-typed text are never rewritten.

_ZH_EN: dict[str, str] = {
    "模型与推理": "Models & reasoning",
    "权限与安全": "Permissions & safety",
    "提示词与输出": "Prompt & output",
    "会话与扩展": "Sessions & extensions",
    "外观与界面": "Appearance & UI",
    "运行参数": "Runtime",
    "新会话默认模型": "Default model for new sessions",
    "推理强度 (--effort / effortLevel)": "Reasoning effort (--effort / effortLevel)",
    "推理强度上限": "Maximum reasoning effort",
    "按模型的 modelSettings (JSON)": "Per-model modelSettings (JSON)",
    "备用模型 (--fallback-model)": "Fallback model (--fallback-model)",
    "允许的模型列表": "Allowed models",
    "禁用的模型列表": "Disabled models",
    "强制开启扩展思考": "Force extended thinking",
    "显示思考摘要": "Show thinking summaries",
    "快速模式": "Fast mode",
    "每会话选择快速模式": "Choose fast mode per session",
    "Advisor 模型": "Advisor model",
    "提示词缓存 TTL": "Prompt cache TTL",
    "子代理缓存 TTL": "Subagent cache TTL",
    "切换模型时自动换挡": "Adjust effort automatically when switching models",
    "自动压缩窗口 (--autocompact)": "Auto-compact window (--autocompact)",
    "启用自动压缩": "Enable auto-compaction",
    "单次预算上限 USD (--max-budget-usd)": "Per-run budget cap, USD (--max-budget-usd)",
    "结构化输出 JSON Schema (--json-schema)": "Structured output JSON Schema (--json-schema)",
    "图片附件传给模型的方式": "How image attachments reach the model",
    "权限模式 (--permission-mode)": "Permission mode (--permission-mode)",
    "审批方式 (--permission-prompts)": "Approval mode (--permission-prompts)",
    "审批等待超时（秒）": "Approval timeout (seconds)",
    "允许的工具 (--allowedTools / permissions.allow)":
        "Allowed tools (--allowedTools / permissions.allow)",
    "禁止的工具 (--disallowedTools / permissions.deny)":
        "Blocked tools (--disallowedTools / permissions.deny)",
    "需要询问的工具 (permissions.ask)": "Tools that always ask (permissions.ask)",
    "内置工具集合 (--tools)": "Built-in tool set (--tools)",
    "附加工作目录 (--add-dir)": "Extra working directories (--add-dir)",
    "跳过所有权限检查": "Skip every permission check",
    "允许手动跳过权限": "Allow manual permission skips",
    "禁用 bypass 模式": "Disable bypass mode",
    "直接拒绝而非询问": "Deny instead of asking",
    "禁止读取工作目录之外": "Block reads outside the working directory",
    "禁止写入工作目录之外": "Block writes outside the working directory",
    "受限模式 (--restricted)": "Restricted mode (--restricted)",
    "安全模式 (--safe-mode)": "Safe mode (--safe-mode)",
    "极简模式 (--bare)": "Bare mode (--bare)",
    "移除动态系统提示段": "Drop the dynamic system-prompt section",
    "sandbox 配置 (JSON)": "Sandbox settings (JSON)",
    "autoMode 配置 (JSON)": "autoMode settings (JSON)",
    "禁用 auto mode": "Disable auto mode",
    "跳过自动权限提示": "Skip automatic permission prompts",
    "Plan 模式中使用 auto": "Use auto in plan mode",
    "完全替换系统提示词 (--system-prompt)": "Replace the system prompt (--system-prompt)",
    "追加系统提示词 (--append-system-prompt)":
        "Append to the system prompt (--append-system-prompt)",
    "系统提示词快照": "System prompt snapshot",
    "输出风格 (outputStyle)": "Output style (outputStyle)",
    "语言 (language)": "Language (language)",
    "简体中文": "Simplified Chinese",
    "CLI 主题 (theme)": "CLI theme (theme)",
    "显示 spinner 提示": "Show spinner tips",
    "减少动效": "Reduce motion",
    "编辑模式 (editorMode)": "Editor mode (editorMode)",
    "commit 加 Co-Authored-By": "Add Co-Authored-By to commits",
    "详细日志 (--verbose)": "Verbose logging (--verbose)",
    "调试过滤 (--debug)": "Debug filter (--debug)",
    "生成下一步建议 (--prompt-suggestions)": "Suggest next steps (--prompt-suggestions)",
    "回显用户消息": "Echo user messages",
    "转发子代理文本/思考": "Forward subagent text and thinking",
    "输出流式分片": "Emit streaming chunks",
    "输出 hook 生命周期事件": "Emit hook lifecycle events",
    "禁用 slash 命令与 skills": "Disable slash commands and skills",
    "跳过 WebFetch 预检": "Skip the WebFetch preflight",
    "禁用 Artifact 工具": "Disable the Artifact tool",
    "设置来源 (--setting-sources)": "Settings sources (--setting-sources)",
    "继续最近会话 (--continue)": "Continue the latest session (--continue)",
    "恢复时创建新会话 ID (--fork-session)":
        "New session id when resuming (--fork-session)",
    "会话显示名 (--name)": "Session display name (--name)",
    "固定会话 ID (--session-id, UUID)": "Fixed session id (--session-id, UUID)",
    "不保存会话 (--no-session-persistence)":
        "Do not persist the session (--no-session-persistence)",
    "自定义子代理 (--agents, JSON/文件)": "Custom subagents (--agents, JSON or file)",
    "指定子代理 (--agent)": "Pick a subagent (--agent)",
    "MCP 配置 (--mcp-config)": "MCP config (--mcp-config)",
    "仅用 --mcp-config 的 MCP": "Use only the MCP servers from --mcp-config",
    "启用全部项目 MCP": "Enable every project MCP server",
    "启用的 .mcp.json 服务": "Enabled .mcp.json servers",
    "禁用的 .mcp.json 服务": "Disabled .mcp.json servers",
    "插件目录 (--plugin-dir)": "Plugin directory (--plugin-dir)",
    "插件 URL (--plugin-url)": "Plugin URL (--plugin-url)",
    "禁用全部 hooks": "Disable all hooks",
    "附加 env 变量 (JSON)": "Extra env vars (JSON)",
    "Chrome 集成": "Chrome integration",
    "自动连接 IDE (--ide)": "Auto-connect an IDE (--ide)",
    "会话保留天数": "Session retention (days)",
    "自动记忆": "Automatic memory",
    "默认工作目录": "Default working directory",
    "单轮超时（秒）": "Per-turn timeout (seconds)",
    "工具调用策略": "Tool-call policy",
    "界面配色": "UI palette",
    "显示思考过程": "Show the thinking process",
    "显示思考链时间线": "Show the thinking timeline",
    "显示工具调用卡片": "Show tool-call cards",
    "显示工具返回结果": "Show tool results",
    "消息视图": "Message view",
    "重启后恢复会话列表": "Restore the session list after a restart",
    "界面字号比例": "UI font scale",
    "模型选择": "Model selection",
    "Hermes 全量模型目录 · 输入框右下角":
        "Full Hermes model catalogue · bottom-right of the composer",
    "多轮上下文": "Multi-turn context",
    "流式输出": "Streaming output",
    "--output-format stream-json + 协议桥 SSE":
        "--output-format stream-json, then bridge SSE",
    "工具调用": "Tool calls",
    "思考过程 / 思考链": "Thinking process and chain",
    "上游 reasoning_content 旁路 + CLI thinking blocks":
        "Upstream reasoning_content side channel + CLI thinking blocks",
    "扩展思考": "Extended thinking",
    "附件（图片/视频/文件）": "Attachments (image, video, file)",
    "@路径注入 + OpenAI vision，失败自动降级":
        "@-path injection + OpenAI vision, with an automatic fallback",
    "一键升级 Claude Code": "One-click Claude Code upgrade",
    "npm install @latest 或 claude update + 版本复核":
        "npm install @latest or claude update, then a version re-check",
    "权限模式": "Permission modes",
    "6 种模式 + 权限提示策略": "Six modes plus an approval-prompt strategy",
    "系统提示词 / 输出风格": "System prompt and output style",
    "会话设置 / 工作目录 / 超时": "Session settings, working directory, timeout",
    "settings.json 全量键": "Every settings.json key",
    "设置页按官方键名生成，--settings 注入，不改用户文件":
        "The settings page is generated from the official key names and injected "
        "through --settings, so your own files are never rewritten",
    "结构化输出 / 预算上限": "Structured output and budget cap",
    "调试 / verbose / hook 事件": "Debug, verbose and hook events",
    "沙箱 / 安全模式": "Sandbox and safe mode",
    "slash 命令（/compact 等）": "Slash commands (/compact and friends)",
    "⌘K 命令面板提供可执行子集；纯 TUI 交互命令不可复现":
        "The ⌘K palette exposes the runnable subset; TUI-only interactive "
        "commands cannot be reproduced",
    "交互式审批弹窗": "Interactive approval dialogs",
    "--permission-prompts host + --permission-prompt-tool MCP 桥，插件内允许/始终允许/拒绝 + 超时自动拒绝":
        "--permission-prompts host plus a --permission-prompt-tool MCP bridge: "
        "Allow, Always allow or Deny inside the plugin, with an automatic deny on timeout",
    "Esc Esc 回滚 / checkpoint": "Esc Esc rollback and checkpoints",
    "交互式 TUI 能力；可用 --resume 到历史会话替代":
        "A TUI-only capability; resume into a past session with --resume instead",
    "内置终端 / diff 窗格 / 文件树": "Built-in terminal, diff pane, file tree",
    "属宿主 UI；插件是消息式工作区，不提供多窗格":
        "That is host UI; this plugin is a message-style workspace with no split panes",
    "云端会话 / 定时任务 / 连接器": "Cloud sessions, scheduled jobs, connectors",
    "需官方账号与订阅；本插件走本机 Hermes 凭据":
        "Needs an official account and subscription; this plugin uses your local "
        "Hermes credentials instead",
    "长驻 MCP 连接 / 后台任务": "Long-lived MCP connections and background jobs",
    "每轮独立进程，MCP 与后台 bash 每轮重建":
        "One process per turn, so MCP servers and background bash are rebuilt every turn",
    "install.cjs 不存在（包不完整）": "install.cjs is missing (incomplete package)",
    "回收站里没有该会话": "That session is not in the trash",
    "手机与电脑连同一个 Wi-Fi，用浏览器打开上面的链接，或直接扫码。口令是固定的，只有 IP 会随重启变化——变了就回来再扫一次。":
        "Phone and computer must be on the same Wi-Fi. Open the link above in a "
        "browser, or scan the code. The passphrase never changes — only the IP does "
        "after a restart, so come back and scan again if it moved.",
    "留空则使用 Hermes 推荐模型；也可在输入框右下角随时切换":
        "Empty uses the model Hermes recommends; you can also switch at any time "
        "from the bottom-right of the composer",
    "low / medium / high / xhigh / max；留空用模型默认":
        "low / medium / high / xhigh / max; empty keeps the model default",
    '如 {"claude-opus-5-5":{"effortLevel":"high"}}':
        'e.g. {"claude-opus-5-5":{"effortLevel":"high"}}',
    "主模型不可用时自动降级": "Fall back automatically while the primary model is unavailable",
    "留空=全部；逗号或换行分隔": "Empty means all; separate entries with commas or newlines",
    "逗号或换行分隔": "Separate entries with commas or newlines",
    "image_url=OpenAI vision 多模态；text=仅注入文本路径（兼容性更好）":
        "image_url sends OpenAI vision multimodal parts; text injects the path only "
        "(more compatible)",
    "host=在插件内弹出审批卡片，由你点允许/拒绝；none=不询问，需审批的工具直接被拒绝":
        "host shows an approval card inside the plugin for you to allow or deny; "
        "none never asks and denies any tool that needs approval",
    "超时无人响应则自动拒绝，避免 headless CLI 永久挂起":
        "Auto-deny when nobody answers, so a headless CLI can never hang forever",
    "逗号或换行分隔，如 Bash(git *) Edit Read":
        "Separate with commas or newlines, e.g. Bash(git *) Edit Read",
    "审批方式为 host 时自动注入默认列表；ask 规则优先于 allowedTools 与用户 settings 的 allow":
        "Injected automatically while the approval mode is host; ask rules win over "
        "allowedTools and the allow list in your own settings",
    "留空=默认；default=默认集；__none__=禁用全部；或 Bash,Edit,Read":
        "Empty means default; default is the default set; __none__ disables all of "
        "them; otherwise a list such as Bash,Edit,Read",
    "逗号或换行分隔的绝对路径": "Absolute paths, separated by commas or newlines",
    "仅建议在隔离沙箱中使用": "Only recommended inside an isolated sandbox",
    "禁用 CLAUDE.md / skills / plugins / hooks / MCP":
        "Disables CLAUDE.md, skills, plugins, hooks and MCP",
    "留空用 Claude Code 默认；替换后工具上下文可能丢失":
        "Empty keeps the Claude Code default; replacing it can lose tool context",
    "推荐：在默认提示词后追加指令": "Recommended: append instructions after the default prompt",
    "如 Explanatory / Learning": "e.g. Explanatory / Learning",
    "已废弃，官方建议用 attribution": "Deprecated upstream in favour of attribution",
    "如 hooks,mcp": "e.g. hooks,mcp",
    "与 resume 互斥": "Mutually exclusive with resume",
    "填名称或 auto；留空不启用": "A name, or auto; empty disables it",
    "JSON 字符串或配置文件路径": "A JSON string or a path to a config file",
    '如 {"PreToolUse":[{"matcher":"Bash","hooks":[...]}]}':
        'e.g. {"PreToolUse":[{"matcher":"Bash","hooks":[...]}]}',
    '如 {"MY_FLAG":"1"}；桥所需的 ANTHROPIC_* 由插件强制写入，不可覆盖':
        'e.g. {"MY_FLAG":"1"}; the ANTHROPIC_* values the bridge needs are written by '
        'the plugin and cannot be overridden',
    "留空则用 Hermes 的 terminal.cwd，再退回用户主目录":
        "Empty uses Hermes' terminal.cwd, then your home directory",
    "auto=把工具 schema 发给模型；describe=仅文字描述工具；off=不提供工具":
        "auto sends the tool schemas to the model; describe only describes the tools "
        "in text; off provides no tools at all",
    "claude=Claude 官方珊瑚橙+暖白；hermes=跟随宿主主题":
        "claude uses Anthropic coral on warm white; hermes follows the host theme",
}

# Fragments: matched inside a longer, value-concatenated string, longest first.
_ZH_EN_FRAG: list[tuple[str, str]] = [
    ("[Hermes 模型网关错误] ", "[Hermes model gateway error] "),
    ("安装损坏 · ", "Install broken · "),
    ("可执行文件不存在", "executable not found"),
    ("文件只有 ", "File is only "),
    (" 字节，已损坏", " bytes — corrupted"),
    ("未命名会话", "Untitled session"),
    ("找不到该会话", "session not found"),
    ("会话 ID 不合法", "invalid session id"),
    ("回收站是空的", "the trash is empty"),
    ("缺少目标项目", "missing target project"),
    ("目标项目不存在", "target project does not exist"),
    ("目标项目里已有同 ID 的会话", "the target project already has a session with this id"),
    ("- 项目：`", "- Project: `"),
    ("- 会话 ID：`", "- Session id: `"),
    ("- 轮次：", "- Turns: "),
    (" · 工具调用：", " · tool calls: "),
    ("[用户请求]", "[User request]"),
    ("无法读取可执行文件：", "Cannot read the executable: "),
    ("是 npm 占位脚本，原生二进制没装上（", "is an npm shim; the native binary was never installed ("),
    (" 字节）", " bytes)"),
    ("不是有效的 Windows 程序（缺少 MZ 头）", "is not a valid Windows program (no MZ header)"),
    ("(无输出)", "(no output)"),
    ("当前安装已损坏，没有可备份的可用版本",
     "The current install is broken; there is no working version to back up"),
    ("没有 claude.exe 进程占用安装目录", "No claude.exe process is holding the install directory"),
    ("修复模式：跳过联网重装，只补齐原生二进制",
     "Repair mode: skip the online reinstall, only restore the native binary"),
    ("补跑原生二进制安装脚本（新 npm 会拦截未批准的 postinstall）",
     "Re-running the native binary install script (newer npm blocks unapproved postinstall)"),
    ("尝试直接从平台包复制 claude.exe", "Trying to copy claude.exe straight from the platform package"),
    ("找不到会话 ", "Session not found: "),
    ("（可能已被归档或删除）", " (it may have been archived or deleted)"),
    ("4 秒内已发起 ", "Started "),
    (" 次删除，已暂停以保护历史记录。如果这是误触，请稍后重试。",
     " deletions within 4 seconds and paused to protect your history. "
     "If that was a mis-click, retry in a moment."),
    ("Claude Code 安装不可用（", "The Claude Code install is unusable ("),
    ("Claude Code 不可用（", "Claude Code is unavailable ("),
    ("## 用户", "## User"),
    ("）。请到「设置 → 升级与诊断」点击「修复安装」，或等升级完成后重试。",
     "). Open Settings → Upgrade & diagnostics, click Repair install, or retry once "
     "the upgrade finishes."),
    ("[本轮附件，请使用 Read / Bash 等工具按需读取]",
     "[Attachments for this turn — open them with Read, Bash or similar as needed]"),
    ("请查看并处理以上附件。", "Please review and handle the attachments above."),
    ("已结束占用安装目录的进程：", "Stopped the processes holding the install directory: "),
    ("claude update 未成功，回退到 npm 安装",
     "claude update did not succeed; falling back to an npm install"),
    ("安装后校验失败：", "Post-install check failed: "),
    ("已从 claude-code-win32-x64 复制原生二进制",
     "Copied the native binary out of claude-code-win32-x64"),
    ("升级未完成 · ", "Upgrade incomplete · "),
    ("归档失败：", "Archive failed: "),
    ("删除失败：", "Delete failed: "),
    ("移动失败：", "Move failed: "),
    ("无法打开终端：", "Cannot open a terminal: "),
    ("导出失败：", "Export failed: "),
    ("用户取消了该轮任务", "The user cancelled this turn"),
    ("任务已结束，审批自动取消", "The job ended, so the approval was cancelled"),
    ("已备份当前可用版本 → ", "Backed up the working version → "),
    ("已回滚到升级前的可用版本", "Rolled back to the pre-upgrade working version"),
    ("回滚后仍然不可用", "Still unusable after the rollback"),
    ("（此处上下文被自动压缩，早期内容已折叠）",
     "(Context was auto-compacted here; earlier content collapsed)"),
    ("恢复失败：", "Restore failed: "),
    ("<details><summary>思考过程</summary>", "<details><summary>Thinking</summary>"),
    ("[图片附件：上游不支持多模态，已按路径引用]",
     "[Image attachment: upstream has no vision, referenced by path instead]"),
    ("备份失败（继续升级）：", "Backup failed (continuing the upgrade): "),
    ("回滚失败：", "Rollback failed: "),
    ("<b>需要访问口令</b><p>请用插件里「手机访问」显示的完整链接打开，链接中的 t=… 就是口令。</p>",
     "<b>A passphrase is required</b><p>Open the full link shown under phone access in "
     "the plugin; the t=… part of it is the passphrase.</p>"),
    ("(思考中…)", "(thinking…)"),
    (" 失败，换下一个源重试…", " failed; trying the next source…"),
    ("工具返回 · ", "Tool result · "),
    ("工具返回", "Tool result"),
    ("<details><summary>工具 · ", "<details><summary>Tool · "),
    ("[附件图片：请用 Read 工具按上文给出的路径读取]",
     "[Image attachment: open it with the Read tool at the path given above]"),
]
_ZH_EN_FRAG.sort(key=lambda pair: len(pair[0]), reverse=True)

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _lang(request: Any = None, default: str = "zh") -> str:
    """``?lang=en`` on the request, else ``Accept-Language``, else the default."""
    code = ""
    try:
        code = str((request.query_params.get("lang") or "")).strip().lower()
    except Exception:
        code = ""
    if not code:
        try:
            header = str(request.headers.get("accept-language") or "").lower()
            code = "en" if header.startswith("en") else ("zh" if header else "")
        except Exception:
            code = ""
    return "en" if code.startswith("en") else (default if code.startswith("zh") else default)


def _tr(text: str, lang: str) -> str:
    """English for one display string. Anything without CJK is returned as-is."""
    if lang != "en" or not text or not _CJK_RE.search(text):
        return text
    hit = _ZH_EN.get(text)
    if hit is not None:
        return hit
    out = text
    for zh, en in _ZH_EN_FRAG:
        if zh in out:
            out = out.replace(zh, en)
    return out


def _tr_obj(value: Any, lang: str) -> Any:
    """Translate every string leaf of a response payload, keys untouched."""
    if lang != "en":
        return value
    if isinstance(value, str):
        return _tr(value, lang)
    if isinstance(value, list):
        return [_tr_obj(item, lang) for item in value]
    if isinstance(value, dict):
        return {key: _tr_obj(item, lang) for key, item in value.items()}
    return value



def _f(key, group, label, typ, default, *, flag=None, path=None,
       options=None, help="", kind=None):
    d = {"key": key, "group": group, "label": label, "type": typ,
         "default": default, "help": help}
    if flag:
        d["flag"] = flag
    if path:
        d["path"] = path
    if options is not None:
        d["options"] = options
    if kind:
        d["kind"] = kind
    return d


SCHEMA: list[dict] = [
    # ---- model / inference -------------------------------------------------
    _f("default_model", G_MODEL, "新会话默认模型", "text", "",
       help="留空则使用 Hermes 推荐模型；也可在输入框右下角随时切换", kind="ui"),
    _f("effort", G_MODEL, "推理强度 (--effort / effortLevel)", "select", "",
       flag="--effort", path="effortLevel", options=_EFFORTS,
       help="low / medium / high / xhigh / max；留空用模型默认"),
    _f("max_effort_level", G_MODEL, "推理强度上限", "select", "",
       path="maxEffortLevel", options=_EFFORTS, help="maxEffortLevel"),
    _f("model_settings", G_MODEL, "按模型的 modelSettings (JSON)", "textarea", "",
       path="modelSettings", help='如 {"claude-opus-5-5":{"effortLevel":"high"}}'),
    _f("fallback_model", G_MODEL, "备用模型 (--fallback-model)", "text", "",
       flag="--fallback-model", help="主模型不可用时自动降级"),
    _f("available_models", G_MODEL, "允许的模型列表", "list", [],
       path="availableModels", help="留空=全部；逗号或换行分隔"),
    _f("denied_models", G_MODEL, "禁用的模型列表", "list", [],
       path="deniedModels", help="逗号或换行分隔"),
    _f("always_thinking_enabled", G_MODEL, "强制开启扩展思考", "switch", True,
       path="alwaysThinkingEnabled", help="alwaysThinkingEnabled"),
    _f("show_thinking_summaries", G_MODEL, "显示思考摘要", "switch", True,
       path="showThinkingSummaries", help="showThinkingSummaries"),
    _f("fast_mode", G_MODEL, "快速模式", "switch", False, path="fastMode"),
    _f("fast_mode_per_session_opt_in", G_MODEL, "每会话选择快速模式", "switch", False,
       path="fastModePerSessionOptIn"),
    _f("advisor_model", G_MODEL, "Advisor 模型", "text", "", path="advisorModel"),
    _f("prompt_cache_ttl", G_MODEL, "提示词缓存 TTL", "select", "",
       path="promptCacheTtl", options=["", "5m", "1h"]),
    _f("subagent_prompt_cache_ttl", G_MODEL, "子代理缓存 TTL", "select", "",
       path="subagentPromptCacheTtl", options=["", "5m", "1h"]),
    _f("ultracode", G_MODEL, "Ultracode", "switch", False, path="ultracode"),
    _f("switch_models_on_flag", G_MODEL, "切换模型时自动换挡", "switch", True,
       path="switchModelsOnFlag"),
    _f("model_overrides", G_MODEL, "modelOverrides (JSON)", "textarea", "",
       path="modelOverrides"),
    _f("model_picker", G_MODEL, "modelPicker (JSON)", "textarea", "", path="modelPicker"),
    _f("model_pricing", G_MODEL, "modelPricing (JSON)", "textarea", "", path="modelPricing"),
    _f("autocompact", G_MODEL, "自动压缩窗口 (--autocompact)", "select", "",
       flag="--autocompact", options=["", "auto", "100000", "200000", "500000", "1000000"]),
    _f("auto_compact_enabled", G_MODEL, "启用自动压缩", "switch", True,
       path="autoCompactEnabled"),
    _f("max_budget_usd", G_MODEL, "单次预算上限 USD (--max-budget-usd)", "text", "",
       flag="--max-budget-usd"),
    _f("json_schema", G_MODEL, "结构化输出 JSON Schema (--json-schema)", "textarea", "",
       flag="--json-schema"),
    _f("betas", G_MODEL, "Beta headers (--betas)", "list", [], flag="--betas"),
    _f("vision_mode", G_MODEL, "图片附件传给模型的方式", "select", "image_url",
       options=["image_url", "text"], kind="runtime",
       help="image_url=OpenAI vision 多模态；text=仅注入文本路径（兼容性更好）"),

    # ---- permissions / security -------------------------------------------
    _f("permission_mode", G_PERM, "权限模式 (--permission-mode)", "select", "acceptEdits",
       flag="--permission-mode", path="permissions.defaultMode", options=_PERMISSION_MODES,
       help="acceptEdits / auto / bypassPermissions / manual / dontAsk / plan"),
    _f("permission_prompts", G_PERM, "审批方式 (--permission-prompts)", "select", "host",
       flag="--permission-prompts", options=["host", "none"],
       help="host=在插件内弹出审批卡片，由你点允许/拒绝；none=不询问，需审批的工具直接被拒绝"),
    _f("approval_timeout", G_PERM, "审批等待超时（秒）", "number", 120,
       kind="runtime", help="超时无人响应则自动拒绝，避免 headless CLI 永久挂起"),
    _f("allowed_tools", G_PERM, "允许的工具 (--allowedTools / permissions.allow)",
       "list", list(ALLOWED_TOOLS), flag="--allowedTools", path="permissions.allow",
       help="逗号或换行分隔，如 Bash(git *) Edit Read"),
    _f("disallowed_tools", G_PERM, "禁止的工具 (--disallowedTools / permissions.deny)",
       "list", [], flag="--disallowedTools", path="permissions.deny"),
    _f("ask_rules", G_PERM, "需要询问的工具 (permissions.ask)", "list", [],
       path="permissions.ask",
       help="审批方式为 host 时自动注入默认列表；ask 规则优先于 allowedTools 与用户 settings 的 allow"),
    _f("tools", G_PERM, "内置工具集合 (--tools)", "text", "", flag="--tools",
       help="留空=默认；default=默认集；__none__=禁用全部；或 Bash,Edit,Read"),
    _f("add_dirs", G_PERM, "附加工作目录 (--add-dir)", "list", [],
       flag="--add-dir", path="permissions.additionalDirectories",
       help="逗号或换行分隔的绝对路径"),
    _f("dangerously_skip_permissions", G_PERM, "跳过所有权限检查", "switch", False,
       flag="--dangerously-skip-permissions", help="仅建议在隔离沙箱中使用"),
    _f("allow_dangerously_skip_permissions", G_PERM, "允许手动跳过权限", "switch", False,
       flag="--allow-dangerously-skip-permissions"),
    _f("disable_bypass_permissions_mode", G_PERM, "禁用 bypass 模式", "select", "",
       path="permissions.disableBypassPermissionsMode", options=["", "disable"]),
    _f("deny_instead_of_prompting", G_PERM, "直接拒绝而非询问", "switch", False,
       path="permissions.denyInsteadOfPrompting"),
    _f("block_reads_outside", G_PERM, "禁止读取工作目录之外", "switch", False,
       path="permissions.blockReadsOutsideWorkingDirectories"),
    _f("block_writes_outside", G_PERM, "禁止写入工作目录之外", "switch", False,
       path="permissions.blockWritesOutsideWorkingDirectories"),
    _f("restricted", G_PERM, "受限模式 (--restricted)", "switch", False, flag="--restricted"),
    _f("safe_mode", G_PERM, "安全模式 (--safe-mode)", "switch", False,
       flag="--safe-mode", help="禁用 CLAUDE.md / skills / plugins / hooks / MCP"),
    _f("bare", G_PERM, "极简模式 (--bare)", "switch", False, flag="--bare"),
    _f("exclude_dynamic_system_prompt_sections", G_PERM, "移除动态系统提示段",
       "switch", False, flag="--exclude-dynamic-system-prompt-sections"),
    _f("sandbox", G_PERM, "sandbox 配置 (JSON)", "textarea", "", path="sandbox"),
    _f("auto_mode", G_PERM, "autoMode 配置 (JSON)", "textarea", "", path="autoMode"),
    _f("disable_auto_mode", G_PERM, "禁用 auto mode", "switch", False, path="disableAutoMode"),
    _f("skip_auto_permission_prompt", G_PERM, "跳过自动权限提示", "switch", False,
       path="skipAutoPermissionPrompt"),
    _f("use_auto_mode_during_plan", G_PERM, "Plan 模式中使用 auto", "switch", False,
       path="useAutoModeDuringPlan"),

    # ---- prompt / output ---------------------------------------------------
    _f("system_prompt", G_PROMPT, "完全替换系统提示词 (--system-prompt)", "textarea", "",
       flag="--system-prompt", help="留空用 Claude Code 默认；替换后工具上下文可能丢失"),
    _f("append_system_prompt", G_PROMPT, "追加系统提示词 (--append-system-prompt)",
       "textarea", "", flag="--append-system-prompt", help="推荐：在默认提示词后追加指令"),
    _f("system_prompt_snapshot", G_PROMPT, "系统提示词快照", "select", "on",
       flag="--system-prompt-snapshot", options=["on", "off"]),
    _f("output_style", G_PROMPT, "输出风格 (outputStyle)", "text", "",
       path="outputStyle", help="如 Explanatory / Learning"),
    _f("language", G_PROMPT, "语言 (language)", "text", "简体中文", path="language"),
    _f("theme", G_PROMPT, "CLI 主题 (theme)", "text", "", path="theme"),
    _f("status_line", G_PROMPT, "statusLine (JSON)", "textarea", "", path="statusLine"),
    _f("spinner_tips_enabled", G_PROMPT, "显示 spinner 提示", "switch", True,
       path="spinnerTipsEnabled"),
    _f("prefers_reduced_motion", G_PROMPT, "减少动效", "switch", False,
       path="prefersReducedMotion"),
    _f("editor_mode", G_PROMPT, "编辑模式 (editorMode)", "select", "",
       path="editorMode", options=["", "vim", "normal"]),
    _f("attribution", G_PROMPT, "attribution (JSON)", "textarea", "", path="attribution"),
    _f("include_co_authored_by", G_PROMPT, "commit 加 Co-Authored-By", "switch", True,
       path="includeCoAuthoredBy", help="已废弃，官方建议用 attribution"),
    _f("verbose", G_PROMPT, "详细日志 (--verbose)", "switch", True, flag="--verbose"),
    _f("debug", G_PROMPT, "调试过滤 (--debug)", "text", "", flag="--debug",
       help="如 hooks,mcp"),
    _f("prompt_suggestions", G_PROMPT, "生成下一步建议 (--prompt-suggestions)",
       "select", "false", flag="--prompt-suggestions", options=["true", "false"]),
    _f("replay_user_messages", G_PROMPT, "回显用户消息", "switch", False,
       flag="--replay-user-messages"),
    _f("forward_subagent_text", G_PROMPT, "转发子代理文本/思考", "switch", True,
       flag="--forward-subagent-text"),
    _f("include_partial_messages", G_PROMPT, "输出流式分片", "switch", True,
       flag="--include-partial-messages"),
    _f("include_hook_events", G_PROMPT, "输出 hook 生命周期事件", "switch", False,
       flag="--include-hook-events"),
    _f("disable_slash_commands", G_PROMPT, "禁用 slash 命令与 skills", "switch", False,
       flag="--disable-slash-commands"),
    _f("skip_web_fetch_preflight", G_PROMPT, "跳过 WebFetch 预检", "switch", False,
       path="skipWebFetchPreflight"),
    _f("disable_artifact", G_PROMPT, "禁用 Artifact 工具", "switch", False,
       path="disableArtifact"),
    _f("api_key_helper", G_PROMPT, "apiKeyHelper", "text", "", path="apiKeyHelper"),

    # ---- session / extensions ---------------------------------------------
    _f("setting_sources", G_SESSION, "设置来源 (--setting-sources)", "text",
       "user,project,local", flag="--setting-sources"),
    _f("continue_session", G_SESSION, "继续最近会话 (--continue)", "switch", False,
       flag="--continue", help="与 resume 互斥"),
    _f("fork_session", G_SESSION, "恢复时创建新会话 ID (--fork-session)", "switch", False,
       flag="--fork-session"),
    _f("session_name", G_SESSION, "会话显示名 (--name)", "text", "", flag="--name"),
    _f("session_id", G_SESSION, "固定会话 ID (--session-id, UUID)", "text", "",
       flag="--session-id"),
    _f("no_session_persistence", G_SESSION, "不保存会话 (--no-session-persistence)",
       "switch", False, flag="--no-session-persistence"),
    _f("worktree", G_SESSION, "git worktree (--worktree)", "text", "", flag="--worktree",
       help="填名称或 auto；留空不启用"),
    _f("agents", G_SESSION, "自定义子代理 (--agents, JSON/文件)", "textarea", "",
       flag="--agents"),
    _f("agent", G_SESSION, "指定子代理 (--agent)", "text", "", flag="--agent"),
    _f("mcp_config", G_SESSION, "MCP 配置 (--mcp-config)", "text", "",
       flag="--mcp-config", help="JSON 字符串或配置文件路径"),
    _f("strict_mcp_config", G_SESSION, "仅用 --mcp-config 的 MCP", "switch", False,
       flag="--strict-mcp-config"),
    _f("enable_all_project_mcp_servers", G_SESSION, "启用全部项目 MCP", "switch", False,
       path="enableAllProjectMcpServers"),
    _f("enabled_mcpjson_servers", G_SESSION, "启用的 .mcp.json 服务", "list", [],
       path="enabledMcpjsonServers"),
    _f("disabled_mcpjson_servers", G_SESSION, "禁用的 .mcp.json 服务", "list", [],
       path="disabledMcpjsonServers"),
    _f("plugin_dirs", G_SESSION, "插件目录 (--plugin-dir)", "list", [],
       flag="--plugin-dir"),
    _f("plugin_urls", G_SESSION, "插件 URL (--plugin-url)", "list", [],
       flag="--plugin-url"),
    _f("enabled_plugins", G_SESSION, "enabledPlugins (JSON)", "textarea", "",
       path="enabledPlugins"),
    _f("extra_known_marketplaces", G_SESSION, "extraKnownMarketplaces (JSON)",
       "textarea", "", path="extraKnownMarketplaces"),
    _f("hooks", G_SESSION, "hooks (JSON)", "textarea", "", path="hooks",
       help='如 {"PreToolUse":[{"matcher":"Bash","hooks":[...]}]}'),
    _f("disable_all_hooks", G_SESSION, "禁用全部 hooks", "switch", False,
       path="disableAllHooks"),
    _f("env_extra", G_SESSION, "附加 env 变量 (JSON)", "textarea", "", path="env",
       help='如 {"MY_FLAG":"1"}；桥所需的 ANTHROPIC_* 由插件强制写入，不可覆盖'),
    _f("chrome", G_SESSION, "Chrome 集成", "select", "",
       options=["", "chrome", "no-chrome"], flag="__chrome__",
       help="--chrome / --no-chrome"),
    _f("ide", G_SESSION, "自动连接 IDE (--ide)", "switch", False, flag="--ide"),
    _f("cleanup_period_days", G_SESSION, "会话保留天数", "number", 30,
       path="cleanupPeriodDays"),
    _f("auto_memory_enabled", G_SESSION, "自动记忆", "switch", True,
       path="autoMemoryEnabled"),

    # ---- runtime -----------------------------------------------------------
    _f("default_cwd", G_RUN, "默认工作目录", "text", "", kind="runtime",
       help="留空则用 Hermes 的 terminal.cwd，再退回用户主目录"),
    _f("timeout", G_RUN, "单轮超时（秒）", "number", 900, kind="runtime"),
    _f("tool_policy", G_RUN, "工具调用策略", "select", "auto",
       options=["auto", "describe", "off"], kind="runtime",
       help="auto=把工具 schema 发给模型；describe=仅文字描述工具；off=不提供工具"),

    # ---- plugin UI ---------------------------------------------------------
    _f("brand_theme", G_UI, "界面配色", "select", "claude", kind="ui",
       options=["claude", "claude-dark", "hermes"],
       help="claude=Claude 官方珊瑚橙+暖白；hermes=跟随宿主主题"),
    _f("show_thinking", G_UI, "显示思考过程", "switch", True, kind="ui"),
    _f("show_thinking_chain", G_UI, "显示思考链时间线", "switch", True, kind="ui"),
    _f("show_tool_cards", G_UI, "显示工具调用卡片", "switch", True, kind="ui"),
    _f("show_tool_results", G_UI, "显示工具返回结果", "switch", True, kind="ui"),
    _f("view_mode", G_UI, "消息视图", "select", "normal", kind="ui",
       options=["normal", "verbose", "compact"]),
    _f("session_persist", G_UI, "重启后恢复会话列表", "switch", True, kind="ui"),
    _f("font_scale", G_UI, "界面字号比例", "number", 1.0, kind="ui"),
]

DEFAULTS: dict[str, Any] = {item["key"]: item["default"] for item in SCHEMA}
_BY_KEY = {item["key"]: item for item in SCHEMA}


def _split_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]
    return []


def _coerce(item: dict, value: Any) -> Any:
    typ = item["type"]
    try:
        if typ == "switch":
            return bool(value)
        if typ == "number":
            return float(value)
        if typ == "list":
            return _split_list(value)
        if typ in ("textarea", "text", "select"):
            return "" if value is None else str(value)
    except Exception:
        return item["default"]
    return value


def _load_settings() -> dict:
    with _SETTINGS_LOCK:
        stored = {}
        try:
            if SETTINGS_FILE.is_file():
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            stored = {}
    out = dict(DEFAULTS)
    for key, item in _BY_KEY.items():
        if key in stored:
            out[key] = _coerce(item, stored[key])
    return out


def _save_settings(values: dict) -> dict:
    clean = {}
    for key, item in _BY_KEY.items():
        if key in values:
            clean[key] = _coerce(item, values[key])
    RUNTIME.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**DEFAULTS, **clean}


def _set_path(payload: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = payload
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _json_value(item: dict, value: Any) -> Any:
    """textarea JSON fields: parse; list fields: list; scalars: as-is."""
    if item["type"] == "textarea":
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None  # invalid JSON is skipped instead of breaking the CLI
    if item["type"] == "list":
        return _split_list(value)
    if item["type"] == "number":
        return int(value) if float(value).is_integer() else float(value)
    return value


# --------------------------------------------------------------------------
# Hermes model catalog / credentials  (unchanged, verified end-to-end)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Per-provider request shaping (opt-in; nothing vendor-specific is hardcoded)
# --------------------------------------------------------------------------
# Some OpenAI-compatible gateways only answer a client that identifies itself
# with extra headers, and a few additionally require the request to be streamed
# and mishandle a plain ``system`` turn. All three are facts about one
# deployment, not about the protocol, so the bridge reads them from config
# instead of baking in a vendor name or a credential.
#
# Preferred place (plugin-owned namespace, cannot shadow a built-in provider):
#
#   plugins:
#     entries:
#       claude-code-parity:
#         providers:
#           <slug>:
#             headers:                 # sent on every bridged request
#               X-Client: my-app
#               X-Request-ID: "{uuid}" # {uuid} is expanded per request
#             stream_only: true        # force stream:true
#             guard_system: true       # keep tool turns from swallowing the prompt
#
# Also accepted, in this order, first hit wins:
#
#   1. CCP_PROVIDER_HEADERS='{"<slug>": {"X-Client": "my-app"}}'   (environment)
#   2. plugins.entries.<this plugin>.providers.<slug>.headers      (config.yaml)
#   3. providers.<slug>.extra_headers                              (Hermes native,
#      the same field the model picker writes for a custom provider)
#
# ``stream_only`` / ``guard_system`` default to true as soon as a slug has any
# configured header, because headers exist precisely because a gateway is
# non-standard — a deployment can still set either to an explicit false.

PLUGIN_NAME = "claude-code-parity"
_PROVIDER_HEADERS_ENV = "CCP_PROVIDER_HEADERS"
_STREAM_ONLY_ENV = "CCP_STREAM_ONLY_PROVIDERS"


def _plugin_cfg() -> dict[str, Any]:
    entries = ((_config().get("plugins") or {}).get("entries") or {})
    entry = entries.get(PLUGIN_NAME) if isinstance(entries, dict) else None
    return entry if isinstance(entry, dict) else {}


def _provider_cfg(slug: str) -> dict[str, Any]:
    """This plugin's shaping block for one provider, falling back to Hermes' own."""
    own = (_plugin_cfg().get("providers") or {}).get(slug)
    if isinstance(own, dict) and own:
        return own
    entry = (_config().get("providers") or {}).get(slug)
    return entry if isinstance(entry, dict) else {}


def _provider_header_spec(slug: str) -> dict[str, Any]:
    raw = os.environ.get(_PROVIDER_HEADERS_ENV, "").strip()
    if raw:
        try:
            table = json.loads(raw)
        except Exception:
            table = {}
        spec = table.get(slug) if isinstance(table, dict) else None
        if isinstance(spec, dict) and spec:
            return spec
    own = (_plugin_cfg().get("providers") or {}).get(slug)
    if isinstance(own, dict):
        for key in ("headers", "extra_headers"):
            spec = own.get(key)
            if isinstance(spec, dict) and spec:
                return spec
    entry = (_config().get("providers") or {}).get(slug)
    if isinstance(entry, dict):
        for key in ("extra_headers", "headers"):
            spec = entry.get(key)
            if isinstance(spec, dict) and spec:
                return spec
    return {}


def _provider_headers(slug: str) -> dict[str, str]:
    """Headers configured for this provider, with ``{uuid}`` expanded per call."""
    out: dict[str, str] = {}
    for name, value in _provider_header_spec(slug).items():
        text = str(value)
        out[str(name)] = str(uuid.uuid4()) if text == "{uuid}" else text
    return out


def _flag(slug: str, key: str) -> bool:
    cfg = _provider_cfg(slug)
    if key in cfg:
        return bool(cfg.get(key))
    # A gateway that needs identifying headers is by definition non-standard.
    return bool(_provider_header_spec(slug))


def _stream_only(slug: str) -> bool:
    raw = os.environ.get(_STREAM_ONLY_ENV, "")
    if slug in {part.strip() for part in raw.split(",") if part.strip()}:
        return True
    return _flag(slug, "stream_only")


def _guard_system(slug: str) -> bool:
    return _flag(slug, "guard_system")


def _pdef(slug: str, ctx: Any = None) -> Any:
    try:
        _ensure_hermes_path()
        from hermes_cli.providers import resolve_provider_full
        from hermes_cli.inventory import load_picker_context
        ctx = ctx or load_picker_context()
        return resolve_provider_full(slug, ctx.user_providers, ctx.custom_providers)
    except Exception:
        return None


def _resolve_target(slug: str, row: dict, ctx: Any = None) -> dict:
    cfg = _config()
    env = _dotenv()
    pool = (_auth().get("credential_pool") or {}).get(slug) or []
    entry = pool[0] if pool else {}
    prov_cfg = (cfg.get("providers") or {}).get(slug) or {}
    pdef = _pdef(slug, ctx)

    base = (entry.get("inference_base_url") or entry.get("base_url")
            or getattr(pdef, "base_url", "") or prov_cfg.get("base_url") or "").rstrip("/")
    token = str(entry.get("access_token") or "")
    if not token:
        token = str(prov_cfg.get("api_key") or "")
    if not token and prov_cfg.get("key_env"):
        token = env.get(str(prov_cfg["key_env"]), "") or os.environ.get(str(prov_cfg["key_env"]), "")
    if not token and getattr(pdef, "api_key_env_vars", None):
        for var in pdef.api_key_env_vars:
            token = env.get(var, "") or os.environ.get(var, "")
            if token:
                break
    if not token and getattr(pdef, "auth_type", "") == "api_key":
        try:
            _ensure_hermes_path()
            from hermes_cli.auth import resolve_api_key_provider_credentials
            creds = resolve_api_key_provider_credentials(slug) or {}
            token = str(creds.get("api_key") or "") or token
        except Exception:
            pass
    if not token and ("127.0.0.1" in base or "localhost" in base):
        token = "local"

    top = cfg.get("model") or {}
    if not base and isinstance(top, dict) and str(top.get("provider") or "") == slug:
        base = str(top.get("base_url") or "").rstrip("/")

    chat_url = base + ("/chat/completions" if base and not base.endswith("/chat/completions") else "")
    return {
        "slug": slug, "name": str(row.get("name") or slug),
        "models": [str(m) for m in (row.get("models") or [])],
        "base_url": base, "chat_url": chat_url, "token": token,
        "headers": _provider_headers(slug),
        "stream_only": _stream_only(slug), "guard_system": _guard_system(slug),
        "local": "127.0.0.1" in base or "localhost" in base,
        "authenticated": bool(row.get("authenticated")),
        "source": str(row.get("source") or ""), "wire": "openai", "has_key": bool(token),
    }


def _catalog(force: bool = False) -> list[dict]:
    global _CATALOG_CACHE
    now = time.time()
    with _RUNTIME_LOCK:
        if not force and _CATALOG_CACHE["groups"] and now - _CATALOG_CACHE["at"] < 90:
            return _CATALOG_CACHE["groups"]
    groups: list[dict] = []
    try:
        _ensure_hermes_path()
        from hermes_cli.inventory import load_picker_context, build_model_options_payload
        # Model discovery always runs against the installation root, never a served
        # profile's trimmed provider list (see _root_home). The lock keeps a concurrent
        # request from seeing the temporary override.
        with _CATALOG_ENV_LOCK:
            prev = os.environ.get("HERMES_HOME")
            reset = None
            try:
                os.environ["HERMES_HOME"] = str(ROOT_HOME)
                try:
                    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
                    reset = set_hermes_home_override(str(ROOT_HOME))
                except Exception:
                    reset = None
                ctx = load_picker_context()
                payload = build_model_options_payload(ctx, include_unconfigured=True)
            finally:
                try:
                    if reset is not None:
                        from hermes_constants import reset_hermes_home_override
                        reset_hermes_home_override(reset)
                except Exception:
                    pass
                if prev is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = prev
        for row in payload.get("providers") or []:
            models = [str(m) for m in (row.get("models") or [])]
            if not models or not row.get("authenticated"):
                continue
            slug = str(row.get("slug") or "")
            try:
                groups.append(_resolve_target(slug, row, ctx))
            except Exception as exc:
                groups.append({
                    "slug": slug, "name": str(row.get("name") or slug), "models": models,
                    "base_url": "", "chat_url": "", "token": "", "headers": {},
                    "stream_only": False, "local": False, "authenticated": True,
                    "source": str(row.get("source") or ""), "wire": "openai",
                    "has_key": False, "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        cfg = _config()
        for slug, prov in (cfg.get("providers") or {}).items():
            if isinstance(prov, dict):
                groups.append(_resolve_target(slug, {
                    "name": prov.get("name") or slug,
                    "models": list((prov.get("models") or {}).keys()),
                    "authenticated": True, "source": "config-fallback",
                }))
        groups.append({"slug": "__error", "name": "catalog", "models": [],
                       "error": f"inventory unavailable: {type(exc).__name__}: {exc}"})
    by_url: dict[str, str] = {}
    for g in groups:
        if g.get("token") and g.get("base_url"):
            by_url.setdefault(g["base_url"], g["token"])
    for g in groups:
        if not g.get("token") and not g.get("local") and g.get("base_url") in by_url:
            g["token"] = by_url[g["base_url"]]
            g["has_key"] = True
            g["key_source"] = "same-endpoint sibling"
    with _RUNTIME_LOCK:
        _CATALOG_CACHE = {"at": now, "groups": groups}
    return groups


def _find_target(provider: str, model: str) -> dict:
    groups = _catalog()
    hit = next((g for g in groups if g["slug"] == provider), None)
    if hit is None:
        hit = next((g for g in groups if model in g["models"]), None)
    if hit is None:
        raise HTTPException(400, f"Unknown Hermes model: {provider}/{model}")
    if model not in hit["models"]:
        raise HTTPException(400, f"Model {model!r} is not in provider {provider!r}")
    if not hit["chat_url"]:
        raise HTTPException(400, f"Provider {provider!r} has no usable endpoint")
    fresh = _resolve_target(hit["slug"], hit)
    if not fresh.get("token") and not fresh.get("local"):
        donor = next((g for g in groups
                      if g["slug"] != provider and g.get("base_url") == fresh.get("base_url")
                      and g.get("token")), None)
        if donor:
            fresh["token"] = donor["token"]
            fresh["has_key"] = True
        for g in groups:
            if g["slug"] != provider and g.get("base_url") == fresh.get("base_url") and g.get("headers"):
                fresh["headers"] = dict(g["headers"])
                fresh["guard_system"] = bool(g.get("guard_system"))
                break
    return fresh


def _probe(group: dict) -> dict:
    slug = group["slug"]
    cached = _PROBE_CACHE.get(slug)
    if cached and time.time() - cached[0] < 90:
        return cached[1]
    result: dict[str, Any] = {"online": False, "status": None, "detail": ""}
    if not group.get("chat_url"):
        result["detail"] = "no endpoint"
    elif not group["models"]:
        result["detail"] = "no models"
    else:
        model = group["models"][0]
        if model in ("default-model", "max-model", "fast-model", "balanced-model", "deep-model"):
            model = next((m for m in group["models"] if m not in (
                "default-model", "max-model", "fast-model", "balanced-model", "deep-model")), model)
        body = {"model": model, "max_tokens": 1, "stream": True,
                "messages": [{"role": "system", "content": "You are a helpful assistant."},
                             {"role": "user", "content": "hi"}]}
        headers = {"content-type": "application/json",
                   "authorization": "Bearer " + (group.get("token") or "local"),
                   **(group.get("headers") or {})}
        try:
            with httpx.stream("POST", group["chat_url"], json=body, headers=headers,
                              timeout=(4.0, 9.0)) as resp:
                result["status"] = resp.status_code
                if resp.status_code == 200:
                    result["online"] = True
                else:
                    result["detail"] = resp.read()[:160].decode("utf-8", "replace").replace("\n", " ")
        except Exception as exc:
            result["detail"] = f"{type(exc).__name__}: {str(exc)[:110]}"
    _PROBE_CACHE[slug] = (time.time(), result)
    return result


# --------------------------------------------------------------------------
# Anthropic <-> OpenAI translation
# --------------------------------------------------------------------------

def _clean_schema(schema: Any) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out = {k: v for k, v in schema.items()
           if k not in ("$schema", "additionalProperties", "definitions", "$defs")}
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    return out


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or b.get("content") or "")
                         for b in content if isinstance(b, dict))
    return ""


def _to_openai(body: dict, model: str, tool_policy: str,
               guard_system: bool = False, vision_mode: str = "image_url") -> dict:
    system = body.get("system")
    if isinstance(system, list):
        sys_text = "\n\n".join(str(b.get("text") or "") for b in system
                               if isinstance(b, dict) and b.get("type") == "text")
    else:
        sys_text = str(system or "")
    sys_text = sys_text.strip() or "You are Claude Code, a helpful coding assistant running inside Hermes Desktop."

    out_msgs: list[dict] = []
    for msg in body.get("messages") or []:
        role = str(msg.get("role") or "user")
        content = msg.get("content")
        if isinstance(content, str):
            out_msgs.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue
        texts: list[str] = []
        images: list[dict] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                texts.append(str(block.get("text") or ""))
            elif btype == "tool_use":
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                tool_calls.append({
                    "id": str(block.get("id") or "toolu_" + uuid.uuid4().hex[:12]),
                    "type": "function",
                    "function": {"name": str(block.get("name") or "tool"),
                                 "arguments": json.dumps(args, ensure_ascii=False)},
                })
            elif btype == "tool_result":
                tool_results.append({
                    "role": "tool", "tool_call_id": str(block.get("tool_use_id") or ""),
                    "content": _text_of(block.get("content")) or "",
                })
            elif btype == "image":
                src = block.get("source") or {}
                if src.get("type") == "base64" and src.get("data"):
                    mime = src.get("media_type") or "image/png"
                    if vision_mode == "image_url":
                        images.append({"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{src['data']}"}})
                    else:
                        texts.append("[附件图片：请用 Read 工具按上文给出的路径读取]")
        if tool_results:
            out_msgs.extend(tool_results)
        if tool_calls:
            # OpenAI requires assistant content to be text/null when tool_calls present.
            out_msgs.append({"role": "assistant", "content": "".join(texts) or None,
                             "tool_calls": tool_calls})
        elif images:
            parts = []
            if texts:
                parts.append({"type": "text", "text": "".join(texts)})
            parts.extend(images)
            out_msgs.append({"role": "user" if role != "user" else role, "content": parts})
        elif texts:
            out_msgs.append({"role": "assistant" if role == "assistant" else role,
                             "content": "".join(texts)})

    if guard_system:
        neutral = ("You are a helpful coding assistant operating inside Hermes Desktop. "
                   "Follow the instructions and use the provided tools.")
        prefix = f"[System instructions — follow exactly]\n{sys_text}\n\n[User request]\n"
        if out_msgs and out_msgs[0].get("role") == "user" and isinstance(out_msgs[0].get("content"), str):
            out_msgs[0]["content"] = prefix + out_msgs[0]["content"]
        else:
            out_msgs.insert(0, {"role": "user", "content": prefix.strip()})
            out_msgs.insert(1, {"role": "assistant", "content": "Understood."})
        messages: list[dict] = [{"role": "system", "content": neutral}] + out_msgs
    else:
        messages = [{"role": "system", "content": sys_text}] + out_msgs

    out: dict[str, Any] = {
        "model": model, "messages": messages,
        "max_tokens": int(body.get("max_tokens") or 8192), "stream": True,
    }
    tools = body.get("tools") or []
    if tool_policy == "auto" and tools:
        out["tools"] = [{
            "type": "function",
            "function": {"name": str(t.get("name") or "tool"),
                         "description": str(t.get("description") or ""),
                         "parameters": _clean_schema(t.get("input_schema"))},
        } for t in tools if isinstance(t, dict)]
        out["tool_choice"] = "auto"
    elif tool_policy == "describe" and tools:
        names = ", ".join(str(t.get("name") or "tool") for t in tools if isinstance(t, dict))
        messages[0]["content"] += f"\n\n[Available tools: {names}]"
    for key in ("temperature", "top_p"):
        if body.get(key) is not None:
            out[key] = body[key]
    if body.get("stop_sequences"):
        out["stop"] = body["stop_sequences"]
    return out


def _strip_images(oa: dict) -> dict:
    """Fallback when an upstream gateway rejects OpenAI vision parts."""
    cleaned = json.loads(json.dumps(oa))
    for m in cleaned.get("messages") or []:
        c = m.get("content")
        if isinstance(c, list):
            parts = []
            for p in c:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    parts.append({"type": "text", "text": "[图片附件：上游不支持多模态，已按路径引用]"})
                else:
                    parts.append(p)
            m["content"] = parts if len(parts) > 1 else (parts[0].get("text", "") if parts else "")
    return cleaned


class _AnthropicStream:
    """Turns OpenAI chat.completion.chunk objects into Anthropic SSE events."""

    def __init__(self, model: str, input_tokens: int = 0) -> None:
        self.msg_id = "msg_" + uuid.uuid4().hex[:24]
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = 0
        self.next_index = 0
        self.text_index: int | None = None
        self.tool_indexes: dict[int, int] = {}
        self.open_blocks: list[int] = []
        self.saw_tool = False
        self.started = False
        self.finished = False
        self.text_parts: list[str] = []
        self.tools: list[dict] = []

    def start(self) -> list[tuple[str, dict]]:
        self.started = True
        return [("message_start", {"type": "message_start", "message": {
            "id": self.msg_id, "type": "message", "role": "assistant",
            "model": self.model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": self.input_tokens, "output_tokens": 0,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        }})]

    def _open_text(self) -> list[tuple[str, dict]]:
        if self.text_index is not None:
            return []
        self.text_index = self.next_index
        self.next_index += 1
        self.open_blocks.append(self.text_index)
        return [("content_block_start", {"type": "content_block_start",
                                         "index": self.text_index,
                                         "content_block": {"type": "text", "text": ""}})]

    def push(self, chunk: dict) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        choices = chunk.get("choices") or []
        if not choices:
            usage = chunk.get("usage") or {}
            if usage.get("prompt_tokens"):
                self.input_tokens = int(usage["prompt_tokens"])
            if usage.get("completion_tokens"):
                self.output_tokens = int(usage["completion_tokens"])
            return out
        delta = choices[0].get("delta") or {}
        text = delta.get("content")
        if text:
            out += self._open_text()
            self.text_parts.append(text)
            self.output_tokens += max(1, len(text) // 3)
            out.append(("content_block_delta", {
                "type": "content_block_delta", "index": self.text_index,
                "delta": {"type": "text_delta", "text": text}}))
        for call in delta.get("tool_calls") or []:
            idx = int(call.get("index") or 0)
            fn = call.get("function") or {}
            if call.get("id") or (fn.get("name") and idx not in self.tool_indexes):
                block_index = self.next_index
                self.next_index += 1
                self.tool_indexes[idx] = block_index
                self.open_blocks.append(block_index)
                self.saw_tool = True
                tool_id = str(call.get("id") or "toolu_" + uuid.uuid4().hex[:12])
                name = str(fn.get("name") or "tool")
                self.tools.append({"id": tool_id, "name": name, "arguments": ""})
                out.append(("content_block_start", {
                    "type": "content_block_start", "index": block_index,
                    "content_block": {"type": "tool_use", "id": tool_id,
                                      "name": name, "input": {}}}))
            args = fn.get("arguments")
            if args and idx in self.tool_indexes:
                if self.tools:
                    self.tools[-1]["arguments"] += args
                out.append(("content_block_delta", {
                    "type": "content_block_delta", "index": self.tool_indexes[idx],
                    "delta": {"type": "input_json_delta", "partial_json": args}}))
        usage = chunk.get("usage") or {}
        if usage.get("completion_tokens"):
            self.output_tokens = int(usage["completion_tokens"])
        if usage.get("prompt_tokens"):
            self.input_tokens = int(usage["prompt_tokens"])
        return out

    def finish(self) -> list[tuple[str, dict]]:
        if self.finished:
            return []
        self.finished = True
        out: list[tuple[str, dict]] = []
        for index in self.open_blocks:
            out.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
        stop_reason = "tool_use" if self.saw_tool else "end_turn"
        out.append(("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"input_tokens": self.input_tokens,
                      "output_tokens": max(1, self.output_tokens)}}))
        out.append(("message_stop", {"type": "message_stop"}))
        return out

    def complete_body(self) -> dict:
        content: list[dict] = []
        if self.text_parts:
            content.append({"type": "text", "text": "".join(self.text_parts)})
        for tool in self.tools:
            try:
                args = json.loads(tool["arguments"] or "{}")
            except Exception:
                args = {}
            content.append({"type": "tool_use", "id": tool["id"],
                            "name": tool["name"], "input": args})
        return {
            "id": self.msg_id, "type": "message", "role": "assistant",
            "model": self.model, "content": content,
            "stop_reason": "tool_use" if self.saw_tool else "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": self.input_tokens,
                      "output_tokens": max(1, self.output_tokens)},
        }


class _Bridge:
    """A loopback-only Anthropic-compatible endpoint for one Claude Code turn."""

    def __init__(self, target: dict, model: str, tool_policy: str,
                 job: dict, vision_mode: str = "image_url") -> None:
        self.target = target
        self.model = model
        self.tool_policy = tool_policy
        self.job = job
        self.vision_mode = vision_mode
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
        self.server.daemon_threads = True
        self.server.bridge = self  # type: ignore[attr-defined]
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name=f"cc-bridge-{self.port}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass

    def note(self, text: str) -> None:
        with _JOBS_LOCK:
            self.job["events"].append({"kind": "log", "text": text[:600]})

    def emit(self, event: dict) -> None:
        """Side-channel events that must NOT be injected into the Anthropic
        wire protocol (forged thinking blocks break Claude Code). They are
        streamed straight to the Desktop pane as a real thinking/tool chain."""
        with _JOBS_LOCK:
            self.job["events"].append(event)

    def upstream(self, body: dict) -> tuple[dict, dict]:
        oa = _to_openai(body, self.model, self.tool_policy,
                        bool(self.target.get("guard_system")), self.vision_mode)
        headers = {"content-type": "application/json",
                   "authorization": "Bearer " + (self.target.get("token") or "local"),
                   "accept": "text/event-stream",
                   **(self.target.get("headers") or {})}
        return oa, headers


class _BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        return

    @property
    def bridge(self) -> _Bridge:
        return self.server.bridge  # type: ignore[attr-defined]

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _sse(self, event: str, data: dict) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
        try:
            self.wfile.write(payload)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            raise

    def do_GET(self) -> None:
        self._json({"ok": True, "bridge": "claude-code-parity", "model": self.bridge.model})

    def do_POST(self) -> None:
        body = self._read_body()
        if "count_tokens" in self.path:
            text = json.dumps(body.get("messages") or [], ensure_ascii=False)
            self._json({"input_tokens": max(1, len(text) // 4)})
            return
        if "/v1/messages" not in self.path:
            self._json({"type": "error", "error": {"type": "not_found_error",
                                                   "message": self.path}}, 404)
            return
        if body.get("stream"):
            self._stream(body)
        else:
            self._complete(body)

    def _openai_stream(self, body: dict) -> tuple[Any, _AnthropicStream]:
        bridge = self.bridge
        oa, headers = bridge.upstream(body)
        stream = _AnthropicStream(bridge.model, max(1, len(json.dumps(oa, ensure_ascii=False)) // 4))
        client = httpx.Client(timeout=httpx.Timeout(15.0, read=900.0))
        request = client.build_request("POST", bridge.target["chat_url"], json=oa, headers=headers)
        resp = client.send(request, stream=True)
        if resp.status_code != 200:
            detail = resp.read()[:900].decode("utf-8", "replace").replace("\n", " ")
            resp.close()
            # Some gateways reject OpenAI vision parts. Retry once without them.
            has_images = any(
                isinstance(m.get("content"), list)
                and any(isinstance(p, dict) and p.get("type") == "image_url"
                        for p in m["content"])
                for m in oa.get("messages") or [])
            if has_images:
                bridge.note(f"upstream HTTP {resp.status_code} with vision; retrying as text")
                fallback = _strip_images(oa)
                request = client.build_request("POST", bridge.target["chat_url"],
                                               json=fallback, headers=headers)
                resp = client.send(request, stream=True)
                if resp.status_code == 200:
                    return (client, resp), stream
                detail = resp.read()[:900].decode("utf-8", "replace").replace("\n", " ")
                resp.close()
            bridge.note(f"upstream HTTP {resp.status_code}: {detail[:400]}")
            bridge.job["upstream_error"] = f"HTTP {resp.status_code}: {detail[:220]}"
            client.close()
            raise RuntimeError(f"HTTP {resp.status_code}: {detail[:300]}")
        return (client, resp), stream

    def _iter_events(self, resp: Any, stream: _AnthropicStream):
        bridge = self.bridge
        reasoning_buf = ""
        reasoning_total = 0
        tool_seen: set[str] = set()
        last_emit = 0.0
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                if data == "[DONE]":
                    break
                continue
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            # --- real upstream thinking chain (side channel) ---------------
            try:
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                r = (delta.get("reasoning_content") or delta.get("reasoning")
                     or delta.get("thinking") or "")
                if isinstance(r, str) and r:
                    reasoning_total += len(r)
                    reasoning_buf += r
                    now = time.time()
                    if len(reasoning_buf) >= 48 or now - last_emit > 0.7:
                        bridge.emit({"kind": "reasoning_delta", "text": reasoning_buf})
                        reasoning_buf = ""
                        last_emit = now
                for call in delta.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    name = str(fn.get("name") or "tool")
                    cid = str(call.get("id") or name + ":" + str(call.get("index") or 0))
                    if cid not in tool_seen:
                        tool_seen.add(cid)
                        bridge.emit({"kind": "tool_call", "name": name,
                                     "id": cid, "args": str(fn.get("arguments") or "")})
                usage = chunk.get("usage") or {}
                if usage.get("completion_tokens"):
                    bridge.emit({"kind": "usage", "output_tokens": int(usage["completion_tokens"]),
                                 "input_tokens": int(usage.get("prompt_tokens") or 0)})
            except Exception:
                pass
            for event, payload in stream.push(chunk):
                yield event, payload
        if reasoning_buf:
            bridge.emit({"kind": "reasoning_delta", "text": reasoning_buf})
        if reasoning_total:
            bridge.emit({"kind": "reasoning_done", "chars": reasoning_total,
                         "tools": len(tool_seen)})

    def _fail_soft(self, stream: _AnthropicStream, exc: Exception) -> None:
        msg = f"[Hermes 模型网关错误] {str(exc)[:300]}"
        try:
            if not stream.started:
                for event, payload in stream.start():
                    self._sse(event, payload)
            for event, payload in stream._open_text():
                self._sse(event, payload)
            self._sse("content_block_delta", {
                "type": "content_block_delta", "index": stream.text_index,
                "delta": {"type": "text_delta", "text": msg}})
            for event, payload in stream.finish():
                self._sse(event, payload)
        except Exception:
            pass

    def _stream(self, body: dict) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.send_header("connection", "close")
        self.end_headers()
        pair = None
        stream = _AnthropicStream(self.bridge.model,
                                  max(1, len(json.dumps(body, ensure_ascii=False)) // 4))
        try:
            for event, payload in stream.start():
                self._sse(event, payload)
            pair, stream = self._openai_stream(body)
            client, resp = pair
            for event, payload in self._iter_events(resp, stream):
                self._sse(event, payload)
            for event, payload in stream.finish():
                self._sse(event, payload)
        except Exception as exc:
            self.bridge.note(f"bridge error: {type(exc).__name__}: {str(exc)[:300]}")
            self._fail_soft(stream, exc)
        finally:
            if pair:
                try:
                    pair[1].close()
                    pair[0].close()
                except Exception:
                    pass

    def _complete(self, body: dict) -> None:
        pair = None
        stream = _AnthropicStream(self.bridge.model)
        try:
            pair, stream = self._openai_stream(body)
            for _event, _payload in self._iter_events(pair[1], stream):
                pass
            stream.finish()
            self._json(stream.complete_body())
        except Exception as exc:
            self.bridge.note(f"bridge error: {type(exc).__name__}: {str(exc)[:300]}")
            payload = stream.complete_body()
            payload["content"] = [{"type": "text",
                                   "text": f"[Hermes 模型网关错误] {str(exc)[:300]}"}]
            payload["stop_reason"] = "end_turn"
            self._json(payload)
        finally:
            if pair:
                try:
                    pair[1].close()
                    pair[0].close()
                except Exception:
                    pass


# --------------------------------------------------------------------------
# Claude Code process: full settings.json + full CLI argv
# --------------------------------------------------------------------------

def _bridge_env(port: int, model: str) -> dict[str, str]:
    base = f"http://127.0.0.1:{port}"
    return {
        "ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "cc-bridge",
        "ANTHROPIC_MODEL": model, "ANTHROPIC_SMALL_FAST_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "DISABLE_AUTOUPDATER": "1", "DISABLE_AUTOUPDATE": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


def _write_settings(key: str, port: int, model: str, values: dict) -> Path:
    """Generate the per-session settings.json from the full plugin schema.

    Never touches ~/.claude/settings.json. The bridge env vars are always
    written last so user-supplied env cannot break the protocol bridge.
    """
    RUNTIME.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"model": model}

    user_env: dict[str, str] = {}
    raw_env = _json_value(_BY_KEY["env_extra"], values.get("env_extra"))
    if isinstance(raw_env, dict):
        user_env = {str(k): str(v) for k, v in raw_env.items()}

    for item in SCHEMA:
        path = item.get("path")
        if not path or item["key"] == "env_extra":
            continue
        skey = item["key"]
        value = values.get(skey, item["default"])
        default = item["default"]
        typ = item["type"]

        # Only write settings the user actually customized. Dumping all 100+
        # defaults into a --settings file destabilises the CLI in headless
        # mode: an explicit `"disableAutoMode": false` (verified on 2.1.322)
        # makes Claude Code enter an endless api_retry loop before it ever
        # calls the bridge. An explicit `false` switch is also semantically
        # identical to the CLI default, so skipping it loses nothing.
        if value == default:
            continue
        if typ == "switch":
            if bool(value):
                _set_path(payload, path, True)
            continue

        parsed = _json_value(item, value)
        if parsed is None or parsed == "" or parsed == []:
            continue
        if path == "permissions.disableBypassPermissionsMode":
            parsed = "disable"
        if path == "permissions.defaultMode" and parsed not in _PERMISSION_MODES:
            continue
        _set_path(payload, path, parsed)

    # Approval mode needs an explicit permissions.ask list. Verified on
    # 2.1.322 that ask rules take precedence over both --allowedTools and the
    # user's ~/.claude/settings.json allow list, so no user config is lost.
    if str(values.get("permission_prompts") or "none") == "host":
        rules = _split_list(values.get("ask_rules")) or list(DEFAULT_ASK_TOOLS)
        payload.setdefault("permissions", {})["ask"] = rules

    payload["env"] = {**user_env, **_bridge_env(port, model)}
    path = RUNTIME / f"settings-{re.sub(r'[^A-Za-z0-9_-]', '', key)}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_argv(values: dict, model: str, settings_path: Path,
                params: dict) -> list[str]:
    """Map every configured CLI flag onto the headless Claude Code command."""
    # The prompt MUST come before variadic options such as --allowedTools /
    # --add-dir: commander greedily consumes every following non-flag token,
    # so a trailing prompt is swallowed and --print exits without input.
    argv = [str(CLAUDE_EXE), "-p"]
    if params.get("text"):
        argv.append(str(params["text"]))
    argv += ["--output-format", "stream-json",
             "--settings", str(settings_path), "--model", model]

    for item in SCHEMA:
        flag = item.get("flag")
        if not flag or flag == "__chrome__" or item["key"] == "permission_prompts":
            continue
        key, typ = item["key"], item["type"]
        value = values.get(key, item["default"])
        if typ == "switch":
            if bool(value):
                argv.append(flag)
            continue
        if typ == "list":
            # CLI variadic options (<tools...>/<directories...>) expect one
            # argv element per value; the next --flag terminates the list.
            parts = _split_list(value)
            if parts:
                argv += [flag] + parts
            continue
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        if key == "tools" and text == "__none__":
            argv += [flag, ""]
            continue
        argv += [flag, text]

    # Chrome integration is two mutually exclusive flags.
    chrome = str(values.get("chrome") or "")
    if chrome == "chrome":
        argv.append("--chrome")
    elif chrome == "no-chrome":
        argv.append("--no-chrome")

    # Session control: --resume wins over --continue.
    resume = params.get("resume_id")
    if resume:
        argv += ["--resume", str(resume)]
        # One-shot fork (the sidebar's "分支" action): derive a NEW session id
        # from this one without flipping the global --fork-session setting.
        if params.get("fork_session") and not bool(values.get("fork_session")):
            argv.append("--fork-session")
    elif bool(values.get("continue_session")):
        argv.append("--continue")

    # Always present: terminates any trailing variadic option. In "host" mode
    # the CLI routes every permission prompt to our MCP approval tool instead
    # of waiting on a TTY; in "none" mode anything that would prompt is denied.
    mode = str(values.get("permission_prompts") or "none")
    argv += ["--permission-prompts", mode]
    if mode == "host" and params.get("mcp_config"):
        # --mcp-config is variadic; the following --flag terminates it.
        argv += ["--mcp-config", str(params["mcp_config"]),
                 "--permission-prompt-tool", APPROVAL_TOOL]
    return argv


def _normalize(obj: dict) -> dict | None:
    kind = obj.get("type")
    if kind == "system" and obj.get("subtype") == "init":
        return {"kind": "init", "session_id": obj.get("session_id"), "model": obj.get("model")}
    if kind == "assistant":
        blocks = ((obj.get("message") or {}).get("content") or [])
        items = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                items.append({"type": "text", "text": block["text"]})
            elif btype == "thinking" and (block.get("thinking") or block.get("signature")):
                items.append({"type": "thinking", "text": block.get("thinking") or "(思考中…)"})
            elif btype == "tool_use":
                items.append({"type": "tool", "name": block.get("name"),
                              "input": block.get("input"), "id": block.get("id")})
        return {"kind": "blocks", "blocks": items} if items else None
    if kind == "user":
        blocks = ((obj.get("message") or {}).get("content") or [])
        items = [{"type": "tool_result", "id": b.get("tool_use_id"),
                  "text": _text_of(b.get("content"))[:2000]}
                 for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        return {"kind": "blocks", "blocks": items} if items else None
    if kind == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                return {"kind": "delta", "text": delta["text"]}
            if delta.get("type") == "thinking_delta" and delta.get("thinking"):
                return {"kind": "thinking_delta", "text": delta["thinking"]}
        return None
    if kind == "result":
        return {"kind": "result", "ok": obj.get("subtype") == "success" and not obj.get("is_error"),
                "text": obj.get("result") or "", "session_id": obj.get("session_id"),
                "usage": obj.get("usage"), "error": obj.get("error")}
    return None


def _push(job: dict, event: dict) -> None:
    with _JOBS_LOCK:
        job["events"].append(event)


# --------------------------------------------------------------------------
# In-plugin approvals (Claude Code --permission-prompt-tool MCP bridge)
# --------------------------------------------------------------------------

def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _prepare_approval(job: dict, values: dict) -> Path:
    """Create a per-turn MCP config + file IPC directory for approval prompts."""
    d = APPROVALS / job["id"]
    d.mkdir(parents=True, exist_ok=True)
    timeout = max(5.0, float(values.get("approval_timeout") or 120))
    cfg = {"mcpServers": {"cc_approval": {
        "type": "stdio", "command": sys.executable,
        "args": [str(MCP_SCRIPT)],
        "env": {"PYTHONUTF8": "1", "CC_APPROVAL_DIR": str(d),
                "CC_APPROVAL_TIMEOUT": str(timeout)},
    }}}
    path = d / "mcp-config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    job["approval_dir"] = d
    job["seen_requests"] = set()
    job["always_allow"] = set()
    threading.Thread(target=_approval_watcher, args=(job,), daemon=True).start()
    return path


def _approval_watcher(job: dict) -> None:
    """Turn MCP request files into poll events; expire timed-out prompts."""
    d: Path | None = job.get("approval_dir")
    if not d:
        return
    while not job["done"]:
        try:
            for f in sorted(d.glob("req-*.json")):
                rid = f.stem[4:]
                if rid in job["seen_requests"]:
                    continue
                try:
                    req = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue  # still being written
                job["seen_requests"].add(rid)
                if (d / f"dec-{rid}.json").is_file():
                    continue
                tool = str(req.get("tool_name") or "unknown")
                if tool in job["always_allow"]:
                    _atomic_json(d / f"dec-{rid}.json", {"action": "allow"})
                    _push(job, {"kind": "permission_resolved", "id": rid,
                                "action": "always_allow", "auto": True, "tool_name": tool})
                    continue
                with _APPROVAL_LOCK:
                    _PENDING[rid] = {"job_id": job["id"], "job": job,
                                     "request": req, "dir": d}
                _push(job, {
                    "kind": "permission_request", "id": rid, "job_id": job["id"],
                    "tool_name": tool, "input": req.get("input") or {},
                    "tool_use_id": req.get("tool_use_id"),
                    "deadline": req.get("deadline"), "timeout": req.get("timeout"),
                })
            now = time.time()
            expired = []
            with _APPROVAL_LOCK:
                for rid, item in list(_PENDING.items()):
                    if item["job_id"] == job["id"] and float(
                            (item["request"] or {}).get("deadline") or 0) <= now:
                        expired.append(rid)
                        _PENDING.pop(rid, None)
            for rid in expired:
                _push(job, {"kind": "permission_resolved", "id": rid, "action": "timeout"})
        except Exception:
            pass
        time.sleep(0.25)


def _cleanup_approval(job: dict) -> None:
    d: Path | None = job.get("approval_dir")
    with _APPROVAL_LOCK:
        for rid, item in list(_PENDING.items()):
            if item["job_id"] == job["id"]:
                _PENDING.pop(rid, None)
    if not d:
        return
    try:
        for f in d.glob("req-*.json"):
            dec = d / f"dec-{f.stem[4:]}.json"
            if not dec.is_file():
                _atomic_json(dec, {"action": "deny", "message": "任务已结束，审批自动取消"})
    except Exception:
        pass

    def _remove() -> None:
        time.sleep(2)
        shutil.rmtree(d, ignore_errors=True)

    threading.Thread(target=_remove, daemon=True).start()


def _run_job(job_id: str, params: dict, target: dict) -> None:
    job = _JOBS[job_id]
    model = params["model"]
    values = params["settings"]
    tool_policy = str(values.get("tool_policy") or params.get("tool_policy") or "auto")
    vision_mode = str(values.get("vision_mode") or "image_url")
    bridge = _Bridge(target, model, tool_policy, job, vision_mode)
    job["bridge"] = bridge
    bridge.start()
    proc = None
    settings_path = None
    try:
        if str(values.get("permission_prompts") or "none") == "host":
            params["mcp_config"] = _prepare_approval(job, values)
        settings_path = _write_settings(job["session_key"], bridge.port, model, values)
        argv = _build_argv(values, model, settings_path, params)
        job["argv"] = argv

        proc_env = os.environ.copy()
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
            proc_env.pop(key, None)
        proc_env.update(_bridge_env(bridge.port, model))
        proc_env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        cwd = (params.get("cwd") or values.get("default_cwd")
               or (_config().get("terminal") or {}).get("cwd") or DEFAULT_CWD)
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=proc_env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job["proc"] = proc
        job["pid"] = proc.pid

        def drain_stderr() -> None:
            try:
                job["stderr"] = (proc.stderr.read() or "")[-4000:]  # type: ignore[union-attr]
            except Exception:
                pass

        threading.Thread(target=drain_stderr, daemon=True).start()

        deadline = time.time() + float(params.get("timeout") or values.get("timeout") or 900)
        saw_text = False
        for line in proc.stdout:  # type: ignore[union-attr]
            if time.time() > deadline:
                proc.kill()
                job["error"] = "timeout"
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                _push(job, {"kind": "log", "text": line[:400]})
                continue
            event = _normalize(obj)
            if not event:
                continue
            if event["kind"] == "init":
                job["session_id"] = event.get("session_id") or job["session_id"]
            if event["kind"] == "delta" or (
                event["kind"] == "blocks"
                and any(b.get("type") == "text" for b in event.get("blocks", []))
            ):
                saw_text = True
            if event["kind"] == "result":
                job["session_id"] = event.get("session_id") or job["session_id"]
                if not saw_text and event.get("text"):
                    _push(job, {"kind": "blocks", "blocks": [{"type": "text", "text": event["text"]}]})
                if not event.get("ok"):
                    job["error"] = str(event.get("error") or "Claude Code reported an error")
            _push(job, event)
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        job["exit_code"] = proc.returncode
        if job["exit_code"] not in (0, None) and not job["error"]:
            job["error"] = f"claude exited with code {job['exit_code']}"
    except Exception as exc:
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        bridge.close()
        job["done"] = True
        job["finished_at"] = time.time()
        _cleanup_approval(job)
        if settings_path:
            try:
                Path(settings_path).unlink(missing_ok=True)
            except Exception:
                pass
        _push(job, {"kind": "done", "error": job["error"]})


# --------------------------------------------------------------------------
# CLI introspection / capability matrix
# --------------------------------------------------------------------------

_SUBCOMMANDS = [
    "agents", "attach", "auth", "auto-mode", "doctor", "gateway", "import",
    "install", "logs", "mcp", "plugin|plugins", "purge", "respawn", "rm",
    "setup-token", "stop|kill", "ultrareview", "update|upgrade",
]

_SLASH_COMMANDS = [
    "/add-dir", "/agents", "/btw", "/chrome", "/clear", "/compact", "/config",
    "/context", "/cost", "/desktop", "/diff", "/doctor", "/effort", "/exit",
    "/export", "/fast", "/feedback", "/help", "/hooks", "/ide", "/init",
    "/insights", "/install-github-app", "/login", "/logout", "/mcp", "/memory",
    "/mobile", "/model", "/permissions", "/plan", "/plugin", "/pr-comments",
    "/privacy-settings", "/release-notes", "/remote-control", "/rename",
    "/resume", "/rewind", "/sandbox", "/security-review", "/stats", "/status",
    "/statusline", "/tasks", "/terminal-setup", "/theme", "/upgrade", "/usage",
    "/vim", "/voice",
]

# Honest capability matrix. "full" = wired to real CLI flags/settings;
# "partial" = GUI equivalent; "limited" = impossible in headless single-turn.
_FEATURES = [
    ("模型选择", "full", "Hermes 全量模型目录 · 输入框右下角"),
    ("多轮上下文", "full", "--resume / --continue / --fork-session"),
    ("流式输出", "full", "--output-format stream-json + 协议桥 SSE"),
    ("工具调用", "full", "--allowedTools / --disallowedTools / --tools / permissions"),
    ("思考过程 / 思考链", "full", "上游 reasoning_content 旁路 + CLI thinking blocks"),
    ("扩展思考", "full", "alwaysThinkingEnabled / showThinkingSummaries / --effort"),
    ("附件（图片/视频/文件）", "full", "@路径注入 + OpenAI vision，失败自动降级"),
    ("一键升级 Claude Code", "full", "npm install @latest 或 claude update + 版本复核"),
    ("权限模式", "full", "6 种模式 + 权限提示策略"),
    ("系统提示词 / 输出风格", "full", "--system-prompt / --append-system-prompt / outputStyle"),
    ("MCP / hooks / plugins / agents", "full", "--mcp-config / hooks / enabledPlugins / --agents"),
    ("会话设置 / 工作目录 / 超时", "full", "--add-dir / --name / --session-id / timeout"),
    ("settings.json 全量键", "full", "设置页按官方键名生成，--settings 注入，不改用户文件"),
    ("结构化输出 / 预算上限", "full", "--json-schema / --max-budget-usd"),
    ("调试 / verbose / hook 事件", "full", "--verbose / --debug / --include-hook-events"),
    ("沙箱 / 安全模式", "full", "--restricted / --safe-mode / --bare / sandbox"),
    ("git worktree / Chrome / IDE", "full", "-w / --chrome / --ide"),
    ("slash 命令（/compact 等）", "partial", "⌘K 命令面板提供可执行子集；纯 TUI 交互命令不可复现"),
    ("交互式审批弹窗", "full", "--permission-prompts host + --permission-prompt-tool MCP 桥，插件内允许/始终允许/拒绝 + 超时自动拒绝"),
    ("Esc Esc 回滚 / checkpoint", "limited", "交互式 TUI 能力；可用 --resume 到历史会话替代"),
    ("内置终端 / diff 窗格 / 文件树", "limited", "属宿主 UI；插件是消息式工作区，不提供多窗格"),
    ("云端会话 / 定时任务 / 连接器", "limited", "需官方账号与订阅；本插件走本机 Hermes 凭据"),
    ("长驻 MCP 连接 / 后台任务", "limited", "每轮独立进程，MCP 与后台 bash 每轮重建"),
]


def _cli_help() -> dict:
    if _CLI_HELP_CACHE.get("data"):
        return _CLI_HELP_CACHE["data"]
    flags: list[str] = []
    version = ""
    problem = _exe_problem(CLAUDE_EXE)
    if problem:
        version = "安装损坏 · " + problem
        data = {"version": version, "flags": flags, "subcommands": _SUBCOMMANDS,
                "slash_commands": _SLASH_COMMANDS,
                "features": [{"name": n, "status": st, "detail": d}
                             for n, st, d in _FEATURES],
                "schema_count": len(SCHEMA),
                "mapped_flags": sorted({i["flag"] for i in SCHEMA if i.get("flag")
                                        and i["flag"] != "__chrome__"}),
                "mapped_settings_keys": sorted({i["path"] for i in SCHEMA if i.get("path")})}
        _CLI_HELP_CACHE["data"] = data
        return data
    try:
        out = subprocess.run([str(CLAUDE_EXE), "--help"], capture_output=True,
                            text=True, timeout=20, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for m in re.finditer(r"(?m)^\s+(--[a-z][a-z0-9-]*)", out.stdout or ""):
            if m.group(1) not in flags:
                flags.append(m.group(1))
    except Exception:
        pass
    try:
        v = subprocess.run([str(CLAUDE_EXE), "--version"], capture_output=True,
                           text=True, timeout=15, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        version = (v.stdout or v.stderr or "").strip()[:120]
    except Exception:
        pass
    data = {"version": version, "flags": flags, "subcommands": _SUBCOMMANDS,
            "slash_commands": _SLASH_COMMANDS,
            "features": [{"name": n, "status": s, "detail": d} for n, s, d in _FEATURES],
            "schema_count": len(SCHEMA),
            "mapped_flags": sorted({i["flag"] for i in SCHEMA if i.get("flag")
                                    and i["flag"] != "__chrome__"}),
            "mapped_settings_keys": sorted({i["path"] for i in SCHEMA if i.get("path")})}
    _CLI_HELP_CACHE["data"] = data
    return data


# --------------------------------------------------------------------------
# Attachment storage
# --------------------------------------------------------------------------

_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_UPLOAD = 25 * 1024 * 1024


def _safe_filename(name: str) -> str:
    """Keep Unicode (Chinese) names, strip only path-hostile characters."""
    cleaned = _UNSAFE_NAME.sub("_", str(name or "")).replace(" ", "_").strip("._")[:80]
    return cleaned or "attachment.bin"


def _attachment_kind(mime: str, name: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


def _save_upload(payload: dict) -> dict:
    name = str(payload.get("name") or "attachment.bin")
    data = str(payload.get("data") or "")
    if "," in data and data[:64].startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception as exc:
        raise HTTPException(400, f"invalid base64: {exc}")
    if not raw:
        raise HTTPException(400, "empty upload")
    if len(raw) > _MAX_UPLOAD:
        raise HTTPException(413, "attachment exceeds 25 MB")
    mime = str(payload.get("mime") or mimetypes.guess_type(name)[0] or "application/octet-stream")
    session_key = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_key") or "default"))[:40]
    uid = uuid.uuid4().hex[:10]
    safe = _safe_filename(name)
    folder = UPLOADS / session_key / uid
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe
    path.write_bytes(raw)
    return {
        "id": uid, "name": name, "path": str(path).replace("\\", "/"),
        "mime": mime, "size": len(raw), "kind": _attachment_kind(mime, name),
        "url": f"/api/plugins/{PLUGIN_ID}/uploads/{session_key}/{uid}/{quote(safe)}",
    }


# --------------------------------------------------------------------------
# One-click upgrade
# --------------------------------------------------------------------------

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PLATFORM_PKG = NPM_PKG + "-win32-x64"
# A shipped binary is ~170 MB; anything under 2 MB is the npm placeholder
# stub (`echo "Error: claude native binary not installed."`) or a truncated
# file. Launching one of those makes Windows pop up
# "不支持 16 位应用程序", so we inspect the header instead of executing it.
MIN_EXE_BYTES = 2 * 1024 * 1024
# registry.npmjs.org is unreachable from this network and npmmirror caps
# large tarballs at ~25 KB/s, so try the Tencent mirror first.
REGISTRIES = ("https://mirrors.cloud.tencent.com/npm",
              "https://registry.npmmirror.com",
              "https://registry.npmjs.org")


def _exe_problem(path: Path) -> str:
    """Return '' for a usable PE binary, else a short human reason."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return "可执行文件不存在"
    except OSError as exc:
        return f"无法读取可执行文件：{exc}"
    if size < MIN_EXE_BYTES:
        try:
            head = path.open("rb").read(200).decode("utf-8", "replace")
        except OSError:
            head = ""
        if "native binary not installed" in head or head.startswith("echo "):
            return f"是 npm 占位脚本，原生二进制没装上（{size} 字节）"
        return f"文件只有 {size} 字节，已损坏"
    try:
        with path.open("rb") as fh:
            if fh.read(2) != b"MZ":
                return "不是有效的 Windows 程序（缺少 MZ 头）"
    except OSError as exc:
        return f"无法读取可执行文件：{exc}"
    return ""


def _node_exe() -> str:
    """The Node that ships with Hermes — present even when PATH has none."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    for cand in (Path(local) / "hermes" / "node" / "node.exe",
                 Path.home() / "AppData" / "Local" / "hermes" / "node" / "node.exe"):
        if cand.is_file():
            return str(cand)
    return shutil.which("node") or "node"


def _npm_argv(args: list[str]) -> list[str]:
    """Build a runnable npm command.

    npm 10 (bundled with Hermes' Node) runs lifecycle scripts; npm 12 silently
    blocks them unless allow-listed, which is exactly what left a stub behind.
    Prefer the bundled npm-cli.js; fall back to the .cmd shim via cmd.exe.
    """
    node = _node_exe()
    cli = Path(node).with_name("node_modules") / "npm" / "bin" / "npm-cli.js"
    if cli.is_file():
        return [node, str(cli), *args]
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    if npm.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", npm, *args]
    return [npm, *args]


def _run_stream(cmd: list[str], cwd: Path, timeout: int = 900) -> int:
    _upgrade_log("$ " + " ".join(cmd))
    _upgrade_log(f"cwd = {cwd}")
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )
    for line in proc.stdout:  # type: ignore[union-attr]
        _upgrade_log(line)
    proc.wait(timeout=timeout)
    _upgrade_log(f"exit code = {proc.returncode}")
    return proc.returncode


def _kill_running_cli() -> list[int]:
    """npm cannot replace claude.exe while a session holds it open.

    That is the EPERM/unlink that aborted the previous upgrade halfway and
    left node_modules in a broken state, so clear it before touching files.
    """
    killed: list[int] = []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=25,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
        for line in (out.stdout or "").splitlines():
            cols = [c.strip().strip('"') for c in line.split('","')]
            if len(cols) < 2 or not cols[1].isdigit():
                continue
            pid = cols[1]
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True,
                           timeout=25, creationflags=CREATE_NO_WINDOW)
            killed.append(int(pid))
    except Exception:
        pass
    return killed


def _run_postinstall() -> str:
    """npm >= 12 blocks the wrapper's postinstall, so run install.cjs by hand."""
    wrapper = INSTALL_DIR / "node_modules" / "@anthropic-ai" / "claude-code"
    script = wrapper / "install.cjs"
    if not script.is_file():
        return "install.cjs 不存在（包不完整）"
    try:
        proc = subprocess.run([_node_exe(), str(script)], cwd=str(wrapper),
                              capture_output=True, text=True, timeout=300,
                              encoding="utf-8", errors="replace",
                              creationflags=CREATE_NO_WINDOW)
        text = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return f"exit {proc.returncode} · " + (text[-400:] or "(无输出)")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _copy_platform_binary() -> bool:
    """Last resort: copy claude.exe straight out of the platform package."""
    src = (INSTALL_DIR / "node_modules" / "@anthropic-ai"
           / "claude-code-win32-x64" / "claude.exe")
    try:
        if src.is_file() and not _exe_problem(src):
            shutil.copy2(src, CLAUDE_EXE)
            return True
    except Exception:
        pass
    return False


def _current_version() -> str:
    global _CLAUDE_VERSION
    problem = _exe_problem(CLAUDE_EXE)
    if problem:
        _CLAUDE_VERSION = "安装损坏 · " + problem
        return _CLAUDE_VERSION
    try:
        out = subprocess.run([str(CLAUDE_EXE), "--version"], capture_output=True,
                            text=True, timeout=20, encoding="utf-8", errors="replace",
                            creationflags=CREATE_NO_WINDOW)
        _CLAUDE_VERSION = (out.stdout or out.stderr or "").strip()[:120]
    except Exception as exc:
        _CLAUDE_VERSION = f"ERROR: {exc}"
    return _CLAUDE_VERSION or ""


def _npm_latest() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    try:
        out = subprocess.run(f'"{npm}" view {NPM_PKG} version', capture_output=True,
                            text=True, timeout=35, shell=True, cwd=str(INSTALL_DIR),
                            encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = (out.stdout or "").strip().splitlines()
        return text[-1].strip() if text else ""
    except Exception:
        return ""


def _upgrade_log(line: str) -> None:
    with _UPGRADE_LOCK:
        _UPGRADE["log"].append(line.rstrip()[:500])
        if len(_UPGRADE["log"]) > 200:
            _UPGRADE["log"] = _UPGRADE["log"][-200:]


def _run_upgrade(method: str) -> None:
    """Install the latest CLI and leave a *working* binary behind.

    Three failure modes were seen on this machine and are each handled:
      1. a running session locks bin/claude.exe -> npm dies with EPERM unlink;
      2. npm >= 12 blocks the wrapper's postinstall -> only a 500-byte stub
         is written, and Windows then reports "not a 16-bit application";
      3. registry.npmjs.org is unreachable -> nothing is downloaded at all.
    """
    with _UPGRADE_LOCK:
        _UPGRADE.update({"running": True, "started": time.time(), "log": [],
                         "exit": None, "method": method, "error": "",
                         "before": _UPGRADE.get("before") or "", "after": ""})
    backup = CLAUDE_EXE.with_name("claude.exe.bak")
    try:
        with _UPGRADE_LOCK:
            _UPGRADE["before"] = _current_version()

        if not _exe_problem(CLAUDE_EXE):
            try:
                shutil.copy2(CLAUDE_EXE, backup)
                _upgrade_log(f"已备份当前可用版本 → {backup.name}")
            except Exception as exc:
                _upgrade_log(f"备份失败（继续升级）：{exc}")
        else:
            _upgrade_log("当前安装已损坏，没有可备份的可用版本")

        killed = _kill_running_cli()
        if killed:
            _upgrade_log("已结束占用安装目录的进程：" + ", ".join(str(p) for p in killed))
        else:
            _upgrade_log("没有 claude.exe 进程占用安装目录")

        exit_code = 0
        if method == "cli" and not _exe_problem(CLAUDE_EXE):
            exit_code = _run_stream([str(CLAUDE_EXE), "update"], INSTALL_DIR)
            if exit_code != 0:
                _upgrade_log("claude update 未成功，回退到 npm 安装")
                method = "npm"
        if method == "repair":
            _upgrade_log("修复模式：跳过联网重装，只补齐原生二进制")
        elif method == "npm":
            exit_code = 1
            for index, registry in enumerate(REGISTRIES):
                cmd = _npm_argv(["install", f"{NPM_PKG}@latest", "--include=optional",
                                 "--no-audit", "--no-fund", "--foreground-scripts",
                                 "--registry", registry])
                exit_code = _run_stream(cmd, INSTALL_DIR)
                if exit_code == 0:
                    break
                if index + 1 < len(REGISTRIES):
                    _upgrade_log(f"{registry} 失败，换下一个源重试…")
        with _UPGRADE_LOCK:
            _UPGRADE["exit"] = exit_code

        problem = _exe_problem(CLAUDE_EXE)
        if problem:
            _upgrade_log("安装后校验失败：" + problem)
            _upgrade_log("补跑原生二进制安装脚本（新 npm 会拦截未批准的 postinstall）")
            _upgrade_log(_run_postinstall())
            problem = _exe_problem(CLAUDE_EXE)
        if problem:
            _upgrade_log("尝试直接从平台包复制 claude.exe")
            if _copy_platform_binary() and not _exe_problem(CLAUDE_EXE):
                problem = ""
                _upgrade_log("已从 claude-code-win32-x64 复制原生二进制")
        if problem and backup.is_file() and not _exe_problem(backup):
            try:
                shutil.copy2(backup, CLAUDE_EXE)
                problem = _exe_problem(CLAUDE_EXE)
                _upgrade_log("已回滚到升级前的可用版本" if not problem
                             else "回滚后仍然不可用")
            except Exception as exc:
                _upgrade_log(f"回滚失败：{exc}")
        if problem:
            with _UPGRADE_LOCK:
                _UPGRADE["error"] = "升级未完成 · " + problem

        _CLI_HELP_CACHE.pop("data", None)
        after = _current_version()
        with _UPGRADE_LOCK:
            _UPGRADE["after"] = after
        _upgrade_log(f"version after = {after}")
    except Exception as exc:
        with _UPGRADE_LOCK:
            _UPGRADE["error"] = f"{type(exc).__name__}: {exc}"
        _upgrade_log("ERROR: " + str(exc))
    finally:
        with _UPGRADE_LOCK:
            _UPGRADE["running"] = False


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Session history — the CLI's own transcripts
# --------------------------------------------------------------------------
# Claude Code writes every conversation to
#   ~/.claude/projects/<slugified-cwd>/<sessionId>.jsonl
# one JSON object per line. Nothing in the CLI can list or prune them outside
# the interactive /resume picker, so the dashboard reads those files directly:
# list, reopen (through --resume <id>), rename, archive and delete.

CLAUDE_CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_CONFIG / "projects"
HISTORY_HOME = RUNTIME / "history"
ARCHIVE_DIR = HISTORY_HOME / "archived"
TRASH_DIR = HISTORY_HOME / "trash"
TITLES_FILE = HISTORY_HOME / "titles.json"
FLAGS_FILE = HISTORY_HOME / "flags.json"

_HISTORY_LOCK = threading.Lock()
_DELETE_STAMPS = deque()
_HISTORY_CACHE: dict[str, dict[str, Any]] = {}
_HISTORY_TITLES: dict[str, str] | None = None
_HISTORY_FLAGS: dict[str, Any] | None = None

# Lines the CLI injects itself. They are `type: user` but were never typed by
# a human, so they must not become bubbles or titles.
_HISTORY_NOISE = (
    "<local-command", "<command-name>", "<command-message", "<system-reminder",
    "<user_info", "<memory", "<content_policy", "<task_management",
    "<regional_conventions", "<agent_loop", "<final_answer_instructions",
    "This session is being continued", "Output token limit hit",
    "[Your previous response", "Caveat: The messages below",
    "Please address this message",
)

_SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$")


def _iso_ms(value: Any) -> int:
    if not isinstance(value, str) or len(value) < 19:
        return 0
    try:
        stamp = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return 0
    return int(stamp.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _is_noise(text: str) -> bool:
    head = text.lstrip()
    return any(head.startswith(m) or m in head[:200] for m in _HISTORY_NOISE)


def _one_line(text: str, limit: int = 90) -> str:
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    return flat[:limit]


def _titles() -> dict[str, str]:
    global _HISTORY_TITLES
    if _HISTORY_TITLES is None:
        data = _json_file(TITLES_FILE, {})
        _HISTORY_TITLES = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    return _HISTORY_TITLES


def _json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _decode_project(slug: str) -> str:
    """Best-effort readable project name from the encoded directory name.

    The CLI replaces every separator with '-', so this is only a fallback: the
    authoritative ``cwd`` is stored inside the transcript itself.
    """
    text = slug
    if re.match(r"^[A-Za-z]--", text):
        text = text[0] + ":\\" + text[3:]
    text = text.replace("-", "\\")
    parts = [p for p in text.split("\\") if p]
    return parts[-1] if parts else slug


def _leaf(path_text: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", str(path_text or "")) if p]
    return parts[-1] if parts else ""


def _scan_session(path: Path, project: str) -> dict[str, Any]:
    """Summarise one transcript. Cheap because irrelevant lines are skipped by
    substring before json parsing (blobs and api-request rows dominate size)."""
    try:
        stat = path.stat()
    except OSError:
        return {}
    key = str(path)
    hit = _HISTORY_CACHE.get(key)
    if hit and hit.get("mtime") == stat.st_mtime and hit.get("size") == stat.st_size:
        return dict(hit["row"])

    title = ""
    last_prompt = ""
    cwd = ""
    branch = ""
    version = ""
    model = ""
    created = 0
    updated = 0
    turns = 0
    replies = 0
    tools = 0
    first_user = ""
    preview = ""

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if ('"user"' not in line and '"assistant"' not in line
                        and '"ai-title"' not in line and '"last-prompt"' not in line):
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                kind = obj.get("type")
                stamp = _iso_ms(obj.get("timestamp"))
                if stamp:
                    created = created or stamp
                    updated = max(updated, stamp)
                if kind == "ai-title":
                    cand = obj.get("aiTitle") or obj.get("title") or ""
                    if cand:
                        title = str(cand)
                    continue
                if kind == "last-prompt":
                    cand = obj.get("lastPrompt") or ""
                    if cand:
                        last_prompt = str(cand)
                    continue
                if obj.get("isSidechain"):
                    continue
                message = obj.get("message") or {}
                content = message.get("content")
                if kind == "user":
                    if isinstance(content, str):
                        text = content
                    else:
                        text = " ".join(
                            str(b.get("text") or "") for b in (content or [])
                            if isinstance(b, dict) and b.get("type") == "text")
                    if not text.strip() or _is_noise(text):
                        continue
                    turns += 1
                    if not first_user:
                        first_user = _one_line(text)
                    cwd = cwd or str(obj.get("cwd") or "")
                    branch = branch or str(obj.get("gitBranch") or "")
                    version = version or str(obj.get("version") or "")
                elif kind == "assistant":
                    replies += 1
                    model = model or str(message.get("model") or "")
                    for block in (content or []):
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tools += 1
                        elif block.get("type") == "text" and not preview:
                            preview = _one_line(block.get("text") or "", 140)
    except OSError:
        return {}

    overrides = _titles()
    row = {
        "id": path.stem,
        "title": overrides.get(path.stem) or title or first_user or last_prompt or "未命名会话",
        "auto_title": title,
        "last_prompt": _one_line(last_prompt, 120),
        "preview": preview,
        "project": project,
        "project_label": _leaf(cwd) or _decode_project(project),
        "cwd": cwd,
        "branch": branch,
        "version": version,
        "model": model,
        "turns": turns,
        "replies": replies,
        "tools": tools,
        "bytes": stat.st_size,
        "created": created,
        "updated": updated or int(stat.st_mtime * 1000),
        "renamed": path.stem in overrides,
        "archived": ARCHIVE_DIR in path.parents,
        **_session_flags(path.stem),
    }
    _HISTORY_CACHE[key] = {"mtime": stat.st_mtime, "size": stat.st_size, "row": row}
    return dict(row)


def _all_sessions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in (PROJECTS_DIR, ARCHIVE_DIR):
        if not root.is_dir():
            continue
        for path in root.glob("*/*.jsonl"):
            try:
                row = _scan_session(path, path.parent.name)
            except Exception:
                continue
            if row:
                rows.append(row)
    rows.sort(key=lambda r: (bool(r.get("pinned")), r.get("updated") or 0), reverse=True)
    return rows


def _trash_meta() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not TRASH_DIR.is_dir():
        return out
    for path in TRASH_DIR.glob("*/*.jsonl"):
        meta = _json_file(path.with_suffix(".json"), {})
        out.append({
            "id": path.stem, "project": path.parent.name,
            "deleted": meta.get("deleted") or int(path.stat().st_mtime * 1000),
            "title": meta.get("title") or path.stem,
        })
    out.sort(key=lambda r: r.get("deleted") or 0, reverse=True)
    return out


def _locate(session_id: str) -> Path | None:
    """Find a transcript in the live or archived tree (path-traversal safe)."""
    if not _SID_RE.match(session_id or ""):
        return None
    for root in (PROJECTS_DIR, ARCHIVE_DIR):
        if not root.is_dir():
            continue
        for path in root.glob(f"*/{session_id}.jsonl"):
            return path
    return None


def _history_messages(path: Path) -> list[dict[str, Any]]:
    """Transcript -> the plugin's own message model."""
    out: list[dict[str, Any]] = []
    turn = 0
    seq = 0
    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return out
    with fh:
        for line in fh:
            if '"user"' not in line and '"assistant"' not in line and '"compact"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("isSidechain"):
                continue
            kind = obj.get("type")
            if kind == "system" and obj.get("subtype") == "compact_boundary":
                seq += 1
                out.append({"key": seq, "turn": turn, "role": "log",
                            "text": "（此处上下文被自动压缩，早期内容已折叠）"})
                continue
            message = obj.get("message") or {}
            content = message.get("content")
            if kind == "user":
                texts: list[str] = []
                results: list[dict] = []
                if isinstance(content, str):
                    texts.append(content)
                else:
                    for block in (content or []):
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "text":
                            texts.append(str(block.get("text") or ""))
                        elif block.get("type") == "tool_result":
                            results.append(block)
                clean = "\n".join(t for t in texts if t.strip() and not _is_noise(t))
                if clean.strip():
                    turn += 1
                    seq += 1
                    out.append({"key": seq, "turn": turn, "role": "user", "text": clean})
                for block in results:
                    seq += 1
                    body = _text_of(block.get("content"))
                    out.append({"key": seq, "turn": turn, "role": "tool", "name": "result",
                                "hint": ("工具返回 · " + _one_line(body, 48)) if body else "工具返回",
                                "text": body[:6000]})
            elif kind == "assistant":
                for block in (content or []):
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    seq += 1
                    if btype == "thinking":
                        out.append({"key": seq, "turn": turn, "role": "thinking",
                                    "text": str(block.get("thinking") or "")})
                    elif btype == "text":
                        text = str(block.get("text") or "")
                        if text.strip():
                            out.append({"key": seq, "turn": turn, "role": "assistant", "text": text})
                    elif btype == "tool_use":
                        payload = block.get("input")
                        try:
                            body = json.dumps(payload, ensure_ascii=False, indent=2)
                        except Exception:
                            body = str(payload)
                        out.append({"key": seq, "turn": turn, "role": "tool",
                                    "name": str(block.get("name") or "tool"),
                                    "hint": str(block.get("name") or "tool") + " · " + _one_line(body, 48),
                                    "text": body[:6000]})
    return out


@router.get("/history")
def history(q: str = "", limit: int = 300, archived: bool = False) -> dict[str, Any]:
    """All CLI transcripts, newest first, with plugin-side renames applied."""
    session_rows = _all_sessions()
    needle = (q or "").strip().lower()
    # archived=true means "show ONLY archived" — that is what the sidebar tab
    # labels promise; active/archived counters always describe both trees.
    items = ([r for r in session_rows if r.get("archived")] if archived
             else [r for r in session_rows if not r.get("archived")])
    if needle:
        items = [r for r in items
                 if needle in (r.get("title") or "").lower()
                 or needle in (r.get("project_label") or "").lower()
                 or needle in (r.get("cwd") or "").lower()
                 or needle in (r.get("last_prompt") or "").lower()
                 or needle in (r.get("preview") or "").lower()]
    projects: dict[str, dict[str, Any]] = {}
    for row in session_rows:
        if row.get("archived"):
            continue
        slug = row.get("project") or ""
        entry = projects.get(slug)
        if entry is None:
            entry = {"slug": slug, "label": _leaf(row.get("cwd") or "") or row.get("project_label") or slug,
                     "cwd": row.get("cwd") or "", "count": 0}
            projects[slug] = entry
        entry["count"] += 1
    return {
        "items": items[: max(1, min(int(limit or 300), 2000))],
        "total": len(session_rows),
        "active": sum(1 for r in session_rows if not r.get("archived")),
        "archived": sum(1 for r in session_rows if r.get("archived")),
        "projects": sorted(projects.values(), key=lambda x: -x["count"]),
        "trash": len(_trash_meta()),
        "dir": str(PROJECTS_DIR),
        "available": PROJECTS_DIR.is_dir(),
    }


@router.get("/history/session")
def history_session(id: str) -> dict[str, Any]:
    path = _locate(id)
    if not path:
        raise HTTPException(404, f"找不到会话 {id}（可能已被归档或删除）")
    meta = _scan_session(path, path.parent.name)
    return {"session": meta, "messages": _history_messages(path)}


@router.post("/history/rename")
def history_rename(body: dict[str, Any]) -> dict[str, Any]:
    session_id = str(body.get("id") or "")
    path = _locate(session_id)
    if not path:
        raise HTTPException(404, "找不到该会话")
    title = re.sub(r"\s+", " ", str(body.get("title") or "")).strip()[:120]
    overrides = _titles()
    if title:
        overrides[session_id] = title
    else:
        overrides.pop(session_id, None)
    _write_json_file(TITLES_FILE, overrides)
    return {"ok": True, "id": session_id, "title": title}


@router.post("/history/archive")
def history_archive(body: dict[str, Any], request: Request) -> dict[str, Any]:
    session_id = str(body.get("id") or "")
    _hist_audit("archive" if body.get("archived", True) else "unarchive", session_id, request)
    archived = bool(body.get("archived", True))
    src = _locate(session_id)
    if not src:
        raise HTTPException(404, "找不到该会话")
    already = ARCHIVE_DIR in src.parents
    if archived == already:
        return {"ok": True, "archived": archived, "id": session_id}
    target_root = ARCHIVE_DIR if archived else PROJECTS_DIR
    dest = target_root / src.parent.name / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dest))
    except Exception as exc:
        raise HTTPException(500, f"归档失败：{exc}")
    meta = _json_file(TITLES_FILE, {})
    row = _HISTORY_CACHE.get(str(src))
    if row:
        _HISTORY_CACHE.pop(str(src), None)
        row["row"]["archived"] = archived
        _HISTORY_CACHE[str(dest)] = row
    return {"ok": True, "id": session_id, "archived": archived,
            "path": str(dest), "renamed": session_id in meta}


@router.post("/history/delete")
def history_delete(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Move to the plugin's own trash — transcripts are never unlinked here.

    A burst guard sits in front: transcripts vanished 30 at a time once with no
    access log to blame, so more than 4 deletions inside 4 seconds now aborts
    instead of eating the history.
    """
    session_id = str(body.get("id") or "")
    _hist_audit("delete", session_id, request)
    now = time.time()
    with _HISTORY_LOCK:
        _DELETE_STAMPS.append(now)
        while _DELETE_STAMPS and now - _DELETE_STAMPS[0] > 4.0:
            _DELETE_STAMPS.popleft()
        burst = len(_DELETE_STAMPS)
    if burst > 4:
        _hist_audit("BLOCKED", f"{session_id} burst={burst}", request)
        raise HTTPException(
            429, f"4 秒内已发起 {burst} 次删除，已暂停以保护历史记录。"
                 "如果这是误触，请稍后重试。")
    src = _locate(session_id)
    if not src:
        raise HTTPException(404, "找不到该会话")
    dest = TRASH_DIR / src.parent.name / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    title = ""
    for row in _all_sessions():
        if row.get("id") == session_id:
            title = row.get("title") or ""
            break
    try:
        shutil.move(str(src), str(dest))
    except Exception as exc:
        raise HTTPException(500, f"删除失败：{exc}")
    _write_json_file(dest.with_suffix(".json"),
                     {"deleted": int(time.time() * 1000), "title": title,
                      "project": src.parent.name})
    _HISTORY_CACHE.pop(str(src), None)
    return {"ok": True, "id": session_id, "trash": str(dest)}


@router.get("/history/trash")
def history_trash() -> dict[str, Any]:
    return {"items": _trash_meta(), "dir": str(TRASH_DIR)}


@router.post("/history/restore")
def history_restore(body: dict[str, Any]) -> dict[str, Any]:
    session_id = str(body.get("id") or "")
    if not _SID_RE.match(session_id):
        raise HTTPException(400, "会话 ID 不合法")
    if not TRASH_DIR.is_dir():
        raise HTTPException(404, "回收站是空的")
    for path in TRASH_DIR.glob(f"*/{session_id}.jsonl"):
        dest = PROJECTS_DIR / path.parent.name / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(path), str(dest))
        except Exception as exc:
            raise HTTPException(500, f"恢复失败：{exc}")
        meta = path.with_suffix(".json")
        if meta.is_file():
            try:
                meta.unlink()
            except OSError:
                pass
        return {"ok": True, "id": session_id, "path": str(dest)}
    raise HTTPException(404, "回收站里没有该会话")


@router.post("/history/purge")
def history_purge(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Permanently unlink one trashed transcript (or the whole trash)."""
    session_id = str(body.get("id") or "")
    _hist_audit("purge", session_id or "<ALL>", request)
    removed = 0
    if not TRASH_DIR.is_dir():
        return {"ok": True, "removed": 0}
    targets = (TRASH_DIR.glob(f"*/{session_id}.jsonl") if session_id
               else TRASH_DIR.glob("*/*.jsonl"))
    for path in list(targets):
        try:
            path.unlink()
            meta = path.with_suffix(".json")
            if meta.is_file():
                meta.unlink()
            removed += 1
        except OSError:
            pass
    return {"ok": True, "removed": removed}


def _flags() -> dict[str, Any]:
    """Plugin-side per-session flags (pin / unread). Kept apart from the
    transcript so Claude Code's own files stay untouched."""
    global _HISTORY_FLAGS
    if _HISTORY_FLAGS is None:
        data = _json_file(FLAGS_FILE, {})
        _HISTORY_FLAGS = data if isinstance(data, dict) else {}
    return _HISTORY_FLAGS


def _session_flags(session_id: str) -> dict[str, Any]:
    entry = _flags().get(session_id) or {}
    return {"pinned": bool(entry.get("pinned")), "unread": bool(entry.get("unread"))}


def _hist_audit(action: str, session_id: str, request: Request | None = None) -> None:
    """Append one line per mutating history call.

    Written because transcripts disappeared from disk with no HTTP access log
    to point at the caller (the gateway logs warnings only). The file is tiny
    and is the only way to tell a UI click apart from a runaway retry loop.
    """
    try:
        HISTORY_HOME.mkdir(parents=True, exist_ok=True)
        ua = ""
        ref = ""
        if request is not None:
            ua = (request.headers.get("user-agent") or "")[:90]
            ref = (request.headers.get("referer") or "")[:60]
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {action:<8} {session_id} "
                f"ua={ua} ref={ref}\n")
        with (HISTORY_HOME / "access.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


@router.post("/history/flags")
def history_flags(body: dict[str, Any]) -> dict[str, Any]:
    """Toggle pin / unread. Both are view state, not transcript content."""
    session_id = str(body.get("id") or "")
    if not _SID_RE.match(session_id):
        raise HTTPException(400, "会话 ID 不合法")
    flags = _flags()
    entry = dict(flags.get(session_id) or {})
    if body.get("pinned") is not None:
        entry["pinned"] = bool(body.get("pinned"))
    if body.get("unread") is not None:
        entry["unread"] = bool(body.get("unread"))
    flags[session_id] = entry
    with _HISTORY_LOCK:
        _write_json_file(FLAGS_FILE, flags)
    cached = _HISTORY_CACHE.get(str(_locate(session_id) or ""))
    if cached:
        cached["row"]["pinned"] = bool(entry.get("pinned"))
        cached["row"]["unread"] = bool(entry.get("unread"))
    return {"ok": True, "id": session_id, **_session_flags(session_id)}


@router.post("/history/move")
def history_move(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Move a transcript to another project folder.

    Claude Code resolves ``--resume`` by looking for
    ``projects/<encoded-cwd>/<sessionId>.jsonl``, so moving the file *and*
    reporting the destination cwd is what makes the moved session resume from
    its new project.
    """
    session_id = str(body.get("id") or "")
    project = re.sub(r"[^A-Za-z0-9_.-]", "", str(body.get("project") or ""))
    src = _locate(session_id)
    if not src:
        raise HTTPException(404, "找不到该会话")
    if not project:
        raise HTTPException(400, "缺少目标项目")
    target = (ARCHIVE_DIR if ARCHIVE_DIR in src.parents else PROJECTS_DIR) / project
    if not target.is_dir():
        raise HTTPException(404, "目标项目不存在")
    if target == src.parent:
        return {"ok": True, "id": session_id, "project": project, "moved": False}
    dest = target / src.name
    if dest.exists():
        raise HTTPException(409, "目标项目里已有同 ID 的会话")
    try:
        shutil.move(str(src), str(dest))
    except Exception as exc:
        raise HTTPException(500, f"移动失败：{exc}")
    _HISTORY_CACHE.pop(str(src), None)
    # Report the destination project's real cwd: --resume resolves a session
    # by <encoded-cwd>/<id>.jsonl, so a wrong cwd makes the moved file
    # unreachable. Use the most common cwd in that folder, not the first one.
    tally: dict[str, int] = {}
    for row in _all_sessions():
        if row.get("project") == project and row.get("cwd"):
            tally[row["cwd"]] = tally.get(row["cwd"], 0) + 1
    cwd = max(tally.items(), key=lambda kv: kv[1])[0] if tally else ""
    return {"ok": True, "id": session_id, "project": project, "moved": True,
            "cwd": cwd, "path": str(dest)}


@router.post("/history/terminal")
def history_terminal(body: dict[str, Any]) -> dict[str, Any]:
    """Open the session in a real console window (`claude --resume <id>`)."""
    session_id = str(body.get("id") or "")
    src = _locate(session_id)
    if not src:
        raise HTTPException(404, "找不到该会话")
    problem = _exe_problem(CLAUDE_EXE)
    if problem:
        raise HTTPException(503, f"Claude Code 不可用（{problem}）")
    meta = _scan_session(src, src.parent.name)
    cwd = meta.get("cwd") or DEFAULT_CWD
    if not Path(cwd).is_dir():
        cwd = str(Path.home())
    try:
        subprocess.Popen(
            [str(CLAUDE_EXE), "--resume", session_id], cwd=cwd,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            close_fds=True,
        )
    except Exception as exc:
        raise HTTPException(500, f"无法打开终端：{exc}")
    return {"ok": True, "id": session_id, "cwd": cwd}


@router.post("/history/export")
def history_export(body: dict[str, Any]) -> dict[str, Any]:
    """Write a readable Markdown copy next to the transcript (no overwrite)."""
    session_id = str(body.get("id") or "")
    src = _locate(session_id)
    if not src:
        raise HTTPException(404, "找不到该会话")
    meta = _scan_session(src, src.parent.name)
    lines: list[str] = [f"# {meta.get('title') or session_id}", "",
                        f"- 项目：`{meta.get('cwd') or meta.get('project_label')}`",
                        f"- 会话 ID：`{session_id}`",
                        f"- 轮次：{meta.get('turns')} · 工具调用：{meta.get('tools')}", ""]
    for msg in _history_messages(src):
        role = msg.get("role")
        if role == "user":
            lines += ["## 用户", "", str(msg.get("text") or ""), ""]
        elif role == "assistant":
            lines += ["## Claude", "", str(msg.get("text") or ""), ""]
        elif role == "thinking":
            lines += ["<details><summary>思考过程</summary>", "",
                      str(msg.get("text") or ""), "", "</details>", ""]
        elif role == "tool":
            lines += [f"<details><summary>工具 · {msg.get('hint') or ''}</summary>", "",
                      "```", str(msg.get("text") or "")[:4000], "```", "",
                      "</details>", ""]
    out_dir = src.parent
    stem = re.sub(r"[\\/:*?\"<>|]", "-", str(meta.get("title") or session_id))[:60]
    dest = out_dir / f"{stem}.md"
    index = 2
    while dest.exists():
        dest = out_dir / f"{stem}-{index}.md"
        index += 1
    try:
        dest.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(500, f"导出失败：{exc}")
    return {"ok": True, "path": str(dest), "bytes": dest.stat().st_size}


@router.get("/health")
def health(request: Request) -> dict:
    global _CLAUDE_VERSION
    if _CLAUDE_VERSION is None:
        _current_version()
    lang = _lang(request)
    groups = _catalog()
    problem = _tr(_exe_problem(CLAUDE_EXE), lang)
    # Counts only — never header values. This is the answer to "did my provider
    # shaping config get picked up?", which is otherwise invisible from the UI.
    shaping: dict[str, dict[str, Any]] = {}
    for group in groups:
        slug = str(group.get("slug") or "")
        if not slug or slug in shaping:
            continue
        count = len(_provider_header_spec(slug))
        if count:
            shaping[slug] = {"headers": count,
                             "stream_only": _stream_only(slug),
                             "guard_system": _guard_system(slug)}
    return {
        "ok": not problem, "plugin": PLUGIN_ID,
        "claude": str(CLAUDE_EXE), "claude_version": _CLAUDE_VERSION,
        "claude_ok": not problem, "claude_problem": problem,
        "install_dir": str(INSTALL_DIR), "home": str(HOME),
        "groups": len(groups),
        "models": sum(len(g["models"]) for g in groups if g.get("models")),
        "jobs": len(_JOBS), "schema_count": len(SCHEMA),
        "provider_shaping": shaping,
        "bridge": "anthropic<->openai per-turn loopback",
    }


@router.get("/models")
def models(probe: bool = True, force: bool = False) -> dict:
    groups = _catalog(force=force)
    public: list[dict] = []
    for g in groups:
        public.append({k: v for k, v in g.items() if k not in ("token", "headers")})
    if probe and public:
        with ThreadPoolExecutor(max_workers=min(8, len(public))) as pool:
            results = list(pool.map(_probe, groups))
        for item, result in zip(public, results):
            item.update(result)
    else:
        for item in public:
            item.update({"online": None, "status": None, "detail": ""})
    flat = [{"id": f'{g["slug"]}/{m}', "provider": g["slug"], "model": m,
             "group": g["name"], "online": g.get("online"), "local": g.get("local")}
            for g in public for m in g.get("models", [])]
    cfg = _config().get("model") or {}
    preferred = f'{cfg.get("provider")}/{cfg.get("default")}' if isinstance(cfg, dict) else None
    saved_default = str(_load_settings().get("default_model") or "")
    recommended = next((m["id"] for m in flat if m["id"] == saved_default),
                       next((m["id"] for m in flat if m["id"] == preferred),
                            next((m["id"] for m in flat if m.get("online")),
                                 flat[0]["id"] if flat else None)))
    return {"groups": public, "models": flat, "recommended": recommended,
            "total": len(flat),
            "default_cwd": (_config().get("terminal") or {}).get("cwd") or DEFAULT_CWD}


@router.post("/catalog")
async def catalog(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / "catalog.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2)[:2_000_000], encoding="utf-8")
    return {"ok": True, "bytes": path.stat().st_size}


@router.get("/settings")
def get_settings(request: Request) -> dict:
    values = _load_settings()
    cli = _cli_help()
    return _tr_obj({
        "schema": SCHEMA, "values": values, "defaults": DEFAULTS,
        "groups": [G_MODEL, G_PERM, G_PROMPT, G_SESSION, G_RUN, G_UI],
        "settings_file": str(SETTINGS_FILE),
        "runtime_dir": str(RUNTIME), "uploads_dir": str(UPLOADS),
        "cli": cli,
        "claude_version": _CLAUDE_VERSION or _current_version(),
        "install_dir": str(INSTALL_DIR),
        "user_settings_file": str(Path(os.environ.get("USERPROFILE", str(Path.home())))
                                  / ".claude" / "settings.json"),
    }, _lang(request))


@router.post("/settings")
async def save_settings(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")
    values = body.get("values")
    if not isinstance(values, dict):
        raise HTTPException(400, "values must be an object")
    saved = _save_settings(values)
    _PROBE_CACHE.clear()
    return {"ok": True, "values": saved, "settings_file": str(SETTINGS_FILE)}


@router.post("/settings/reset")
def reset_settings() -> dict:
    saved = _save_settings({})
    return {"ok": True, "values": saved}


@router.get("/cli")
def cli_info(request: Request) -> dict:
    return _tr_obj({**_cli_help(), "claude": str(CLAUDE_EXE),
                    "install_dir": str(INSTALL_DIR), "settings_count": len(SCHEMA)},
                   _lang(request))


@router.post("/upload")
async def upload(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")
    item = _save_upload(body)
    return {"ok": True, "attachment": item}


@router.get("/uploads/{session_key}/{uid}/{name}")
def serve_upload(session_key: str, uid: str, name: str) -> Response:
    session_key = re.sub(r"[^A-Za-z0-9_-]", "", session_key)
    uid = re.sub(r"[^A-Za-z0-9_-]", "", uid)
    name = _safe_filename(unquote(name))
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(404, "invalid attachment name")
    path = UPLOADS / session_key / uid / name
    if not path.is_file():
        raise HTTPException(404, "attachment not found")
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(content=path.read_bytes(), media_type=mime,
                    headers={"cache-control": "no-store"})


@router.get("/upgrade/check")
def upgrade_check() -> dict:
    current = _current_version()
    latest = _npm_latest()
    def nums(s):
        return [int(x) for x in re.findall(r"\d+", s)[:3]]
    try:
        available = bool(latest) and nums(latest) > nums(current)
    except Exception:
        available = False
    with _UPGRADE_LOCK:
        _UPGRADE["latest"] = latest
        _UPGRADE["before"] = current
    return {"ok": True, "current": current, "latest": latest,
            "update_available": available, "install_dir": str(INSTALL_DIR)}


@router.post("/upgrade")
async def upgrade(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    with _UPGRADE_LOCK:
        if _UPGRADE["running"]:
            raise HTTPException(409, "an upgrade is already running")
    requested = str(body.get("method") or "")
    method = "cli" if requested == "cli" else "repair" if requested == "repair" else "npm"
    threading.Thread(target=_run_upgrade, args=(method,), daemon=True).start()
    return {"ok": True, "method": method, "started": True}


@router.get("/upgrade/status")
def upgrade_status(request: Request) -> dict:
    with _UPGRADE_LOCK:
        data = {k: (list(v) if isinstance(v, list) else v)
                for k, v in _UPGRADE.items()}
    data["install_problem"] = _exe_problem(CLAUDE_EXE)
    return _tr_obj(data, _lang(request))


@router.post("/chat")
async def chat(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")
    text = str(body.get("text") or "").strip()
    attachments = body.get("attachments") or []
    if not text and not attachments:
        raise HTTPException(400, "text or attachments are required")
    problem = _exe_problem(CLAUDE_EXE)
    if problem:
        raise HTTPException(
            503,
            _tr(f"Claude Code 安装不可用（{problem}）。请到「设置 → 升级与诊断」点击"
                "「修复安装」，或等升级完成后重试。", _lang(request)))
    target = _find_target(str(body.get("provider") or ""), str(body.get("model") or ""))

    # Attachments become real @file references the CLI can Read, plus a short
    # manifest so the model knows what is available and how to open it.
    refs = []
    for a in attachments:
        if not isinstance(a, dict):
            continue
        p = str(a.get("path") or "").replace("\\", "/")
        if not p or not Path(p).is_file():
            continue
        refs.append(f'- {a.get("name") or Path(p).name} ({a.get("kind") or "file"}, '
                    f'{a.get("mime") or "application/octet-stream"}) → @{p}')
    if refs:
        manifest = ("[本轮附件，请使用 Read / Bash 等工具按需读取]\n" + "\n".join(refs)
                    + "\n\n[用户请求]\n")
        text = manifest + (text or "请查看并处理以上附件。")

    job_id = uuid.uuid4().hex[:12]
    session_key = re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("session_key") or job_id))[:48] or job_id
    job: dict[str, Any] = {
        "id": job_id, "session_key": session_key, "session_id": body.get("resume_id"),
        "events": [], "done": False, "error": None, "exit_code": None,
        "stderr": "", "created_at": time.time(), "proc": None, "pid": None,
        "bridge": None, "argv": [],
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job
        if len(_JOBS) > 40:
            for old in sorted(_JOBS, key=lambda k: _JOBS[k]["created_at"])[:-40]:
                _JOBS.pop(old, None)

    values = _load_settings()
    # Per-request overrides from the toolbar still win over saved settings.
    for key in ("tool_policy", "effort", "view_mode"):
        if body.get(key) is not None and key in _BY_KEY:
            values[key] = _coerce(_BY_KEY[key], body[key])
    params = {
        "text": text, "model": str(body.get("model")),
        "resume_id": body.get("resume_id"), "cwd": body.get("cwd"),
        "fork_session": bool(body.get("fork_session")),
        "timeout": body.get("timeout") or values.get("timeout") or 900,
        "settings": values,
    }
    threading.Thread(target=_run_job, args=(job_id, params, target), daemon=True).start()
    return {"job_id": job_id, "provider": target["slug"], "model": params["model"],
            "base_url": target["base_url"], "local": target["local"],
            "attachments": len(refs)}


@router.get("/poll")
def poll(request: Request, job_id: str, cursor: int = 0) -> dict:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job_id")
    lang = _lang(request)
    with _JOBS_LOCK:
        events = job["events"][cursor:]
    return {
        "events": events, "cursor": cursor + len(events), "done": job["done"],
        "error": _tr(str(job["error"] or ""), lang) or job["error"],
        "session_id": job["session_id"],
        "exit_code": job["exit_code"],
        "stderr": job["stderr"][-800:] if job["done"] else "",
    }


@router.get("/approvals")
def approvals() -> dict:
    """All pending permission prompts across jobs (also prunes expired ones)."""
    now = time.time()
    items = []
    expired = []
    with _APPROVAL_LOCK:
        for rid, item in list(_PENDING.items()):
            req = item["request"] or {}
            if float(req.get("deadline") or 0) <= now:
                expired.append((rid, item))
                _PENDING.pop(rid, None)
                continue
            items.append({
                "id": rid, "job_id": item["job_id"],
                "tool_name": req.get("tool_name"),
                "input": req.get("input") or {},
                "tool_use_id": req.get("tool_use_id"),
                "created_at": req.get("created_at"),
                "deadline": req.get("deadline"),
                "remaining": int(float(req.get("deadline") or now) - now),
            })
    for rid, item in expired:
        _push(item["job"], {"kind": "permission_resolved", "id": rid, "action": "timeout"})
    return {"pending": items, "count": len(items),
            "mode": str(_load_settings().get("permission_prompts") or "none")}


@router.post("/approvals/decide")
async def decide_approval(request: Request) -> dict:
    """Write the decision file the MCP server is waiting for."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")
    rid = str(body.get("id") or "")
    action = str(body.get("action") or "deny")
    if action not in ("allow", "deny", "always_allow"):
        raise HTTPException(400, "action must be allow / deny / always_allow")
    with _APPROVAL_LOCK:
        item = _PENDING.pop(rid, None)
    if not item:
        raise HTTPException(404, "unknown or expired approval id")
    job, d = item["job"], item["dir"]
    payload: dict[str, Any] = {"action": action}
    if isinstance(body.get("updated_input"), dict) and body["updated_input"]:
        payload["updated_input"] = body["updated_input"]
    if body.get("message"):
        payload["message"] = str(body["message"])[:400]
    _atomic_json(d / f"dec-{rid}.json", payload)
    if action == "always_allow":
        job.setdefault("always_allow", set()).add(
            str((item["request"] or {}).get("tool_name") or ""))
    _push(job, {"kind": "permission_resolved", "id": rid, "action": action,
                "tool_name": (item["request"] or {}).get("tool_name")})
    return {"ok": True, "action": action}


@router.post("/cancel")
async def cancel(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    job = _JOBS.get(str(body.get("job_id") or ""))
    if not job:
        raise HTTPException(404, "unknown job_id")
    # Deny any pending prompt first, otherwise the MCP server keeps the CLI
    # alive waiting for a decision even after we kill the parent process.
    d = job.get("approval_dir")
    denied = []
    with _APPROVAL_LOCK:
        for rid, item in list(_PENDING.items()):
            if item["job_id"] == job["id"]:
                denied.append((rid, item["dir"]))
                _PENDING.pop(rid, None)
    for rid, path in denied:
        try:
            _atomic_json(path / f"dec-{rid}.json",
                         {"action": "deny", "message": "用户取消了该轮任务"})
        except Exception:
            pass
        _push(job, {"kind": "permission_resolved", "id": rid, "action": "deny"})
    proc = job.get("proc")
    if proc and proc.poll() is None:
        proc.kill()
        job["error"] = "cancelled"
    return {"ok": True, "denied_approvals": len(denied)}

# --------------------------------------------------------------------------
# Local relay — the desktop window's own door
# --------------------------------------------------------------------------
# Why this exists: the gateway authenticates ``/api/plugins/<id>/*`` with a
# dashboard session cookie (or the native grant on a request the Desktop
# itself signed). When the dashboard has an auth provider configured, the
# Desktop window's plugin REST arrives without either and gets 401 / a
# plugin-looking 404, so the panel shows "backend not connected" while the
# same routes answer fine from a browser. The relay serves the SAME router on
# 127.0.0.1 under a shared token, so the panel works whatever the dashboard's
# auth mode is. The official ``ctx.rest`` door is still tried first.
def _relay_token() -> str:
    """Per-install token for the loopback relay, generated once and persisted.

    This is not a credential to any remote service: it exists so that a random
    web page the user happens to visit cannot drive this loopback API. A value
    committed to the source tree would be public and therefore worthless, so it
    is random per installation and kept in ``.runtime/relay.json``.
    """
    path = RUNTIME / "relay.json"
    try:
        token = str(json.loads(path.read_text(encoding="utf-8")).get("token") or "")
        if token:
            return token
    except Exception:
        pass
    token = secrets.token_urlsafe(24)
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"token": token}, indent=1), encoding="utf-8")
    except Exception:
        pass
    return token


RELAY_TOKEN = _relay_token()
RELAY_PORTS = tuple(range(47823, 47829))

_relay_lock = threading.Lock()
_relay_state: dict[str, Any] = {"started": False, "port": None}


def _relay_port_free(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _start_relay() -> None:
    """Serve this plugin's router on a loopback port, once per process."""
    with _relay_lock:
        if _relay_state["started"]:
            return
        _relay_state["started"] = True
        port = next((p for p in RELAY_PORTS if _relay_port_free(p)), None)
        if port is None:
            return
        try:
            import uvicorn
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            from fastapi.responses import JSONResponse

            relay = FastAPI(title="claude-code-parity relay", docs_url=None,
                            redoc_url=None, openapi_url=None)
            relay.add_middleware(
                CORSMiddleware, allow_origins=[],
                allow_origin_regex=r"^(?:file://.*|app://.*|null)$",
                allow_methods=["*"], allow_headers=["*"], max_age=600,
            )

            @relay.get("/relay/handshake")
            def _relay_handshake(request: Request):
                """Hand the relay token to the Desktop window, and to nobody else.

                The window's own ``fetch`` runs from a ``file://`` / ``app://``
                origin, which is what the CORS policy above admits. A request that
                names an http(s) origin is refused outright, so a page the user
                visits can neither obtain the token nor read a response from here.
                Loopback only, like the rest of the relay.
                """
                host = (request.client.host if request.client else "") or ""
                if host not in ("127.0.0.1", "::1", "localhost"):
                    return JSONResponse(status_code=403, content={"detail": "loopback only"})
                origin = (request.headers.get("origin") or "").strip().lower()
                if origin.startswith("http://") or origin.startswith("https://"):
                    return JSONResponse(status_code=403, content={"detail": "web origins refused"})
                return {"token": RELAY_TOKEN}

            @relay.middleware("http")
            async def _relay_scope(request, call_next):
                """Token check, plus the profile scope this thread does not inherit.

                The gateway is a profile multiplexer: secret reads fail closed unless
                the running task carries a profile's secret scope. A brand-new
                uvicorn thread has none, so ``build_model_options_payload`` saw
                ``UnscopedSecretError`` and the picker shrank to a few providers.
                Bind the install root's own scope for the duration of the request.
                """
                if (request.method != "OPTIONS" and request.url.path != "/relay/handshake"
                        and request.headers.get("x-ccp-token") != RELAY_TOKEN):
                    return JSONResponse(status_code=403, content={"detail": "relay token required"})
                token = None
                fallback = None
                try:
                    from agent.secret_scope import set_secret_scope, set_multiplex_context
                    from tui_gateway.launch_profile_policy import owner_secret_scope
                    home = _root_home()
                    token = set_secret_scope(owner_secret_scope(home), profile_home=str(home))
                except Exception:
                    try:
                        from agent.secret_scope import set_multiplex_context
                        fallback = set_multiplex_context(False)
                    except Exception:
                        fallback = None
                try:
                    return await call_next(request)
                finally:
                    try:
                        if token is not None:
                            from agent.secret_scope import reset_secret_scope
                            reset_secret_scope(token)
                        elif fallback is not None:
                            from agent.secret_scope import reset_multiplex_context
                            reset_multiplex_context(fallback)
                    except Exception:
                        pass

            relay.include_router(router)
            server = uvicorn.Server(uvicorn.Config(
                relay, host="127.0.0.1", port=port, log_level="error",
                access_log=False, lifespan="off",
            ))
            threading.Thread(target=server.run, name="ccp-relay", daemon=True).start()
            _relay_state["port"] = port
        except Exception:
            _relay_state["port"] = None


# --------------------------------------------------------------------------
# Phone access — the same Claude Code panel on the local network
# --------------------------------------------------------------------------
# A second uvicorn instance listens on 0.0.0.0 so a phone on the same Wi-Fi can
# open the workspace. Only a hard allow-list of routes is mounted, and every
# request carries the access token, so /settings, /upgrade and /catalog are not
# reachable from the LAN even though they share the same router object.

MOBILE_PORT = int(os.environ.get("CCP_MOBILE_PORT") or 47830)
MOBILE_FILE = RUNTIME / "mobile.json"
_mobile_lock = threading.Lock()
_mobile_state: dict[str, Any] = {"started": False, "port": None, "token": ""}
_mobile_html_cache: dict[str, str] = {}

MOBILE_ROUTES = {
    "/api/health", "/api/models", "/api/chat", "/api/poll", "/api/cancel",
    "/api/approvals", "/api/approvals/decide", "/api/history",
    "/api/history/session", "/api/upload", "/api/mobile",
}


def _mobile_html() -> str:
    """Load the single-file phone client without relying on sys.path."""
    if "html" in _mobile_html_cache:
        return _mobile_html_cache["html"]
    path = Path(__file__).with_name("mobile_page.py")
    html = "<h1>mobile page missing</h1>"
    try:
        namespace: dict[str, Any] = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        html = str(namespace.get("MOBILE_HTML") or html)
    except Exception:
        pass
    _mobile_html_cache["html"] = html
    return html


def _mobile_token() -> str:
    data = _json_file(MOBILE_FILE, {})
    token = str((data or {}).get("token") or "")
    if not token:
        token = secrets.token_urlsafe(18)
        _write_json_file(MOBILE_FILE, {"token": token, "created": int(time.time())})
    return token


def _lan_ips() -> list[str]:
    """Every IPv4 address a phone on this Wi-Fi could dial."""
    import socket
    found: list[str] = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith(("127.", "169.254.")):
                found.append(ip)
    except Exception:
        pass
    return [ip for ip in found if ip.count(".") == 3]


def _mobile_urls() -> list[str]:
    token = _mobile_state.get("token") or _mobile_token()
    port = _mobile_state.get("port") or MOBILE_PORT
    return [f"http://{ip}:{port}/?t={token}" for ip in _lan_ips()]


def _bind_mobile_scope(request) -> Any:
    """Same profile-secret problem as the relay: a fresh thread has no scope,
    so model discovery would fail closed and the phone would see 5 models."""
    try:
        from agent.secret_scope import set_secret_scope
        from tui_gateway.launch_profile_policy import owner_secret_scope
        home = _root_home()
        return set_secret_scope(owner_secret_scope(home), profile_home=str(home))
    except Exception:
        return None


def _start_mobile() -> None:
    with _mobile_lock:
        if _mobile_state["started"]:
            return
        _mobile_state["started"] = True
        token = _mobile_token()
        _mobile_state["token"] = token
        try:
            import uvicorn
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            from fastapi.responses import HTMLResponse, JSONResponse

            app = FastAPI(title="claude-code-parity phone", docs_url=None,
                          redoc_url=None, openapi_url=None)
            app.add_middleware(CORSMiddleware, allow_origins=["*"],
                               allow_methods=["*"], allow_headers=["*"], max_age=600)

            @app.middleware("http")
            async def _phone_guard(request, call_next):
                if request.method == "OPTIONS":
                    return await call_next(request)
                path = request.url.path
                supplied = (request.query_params.get("t")
                            or request.headers.get("x-ccp-mobile") or "")
                if supplied != token:
                    if path == "/":
                        return HTMLResponse(
                            "<meta name=viewport content='width=device-width'>"
                            "<div style='font:16px/1.7 -apple-system;padding:28px'>"
                            "<b>需要访问口令</b><p>请用插件里「手机访问」显示的完整链接打开，"
                            "链接中的 t=… 就是口令。</p></div>", status_code=403)
                    return JSONResponse({"detail": "token required"}, status_code=403)
                if path != "/" and path not in MOBILE_ROUTES \
                        and not path.startswith("/api/uploads/"):
                    return JSONResponse({"detail": "not exposed on this endpoint"},
                                        status_code=403)
                scope = _bind_mobile_scope(request)
                try:
                    return await call_next(request)
                finally:
                    if scope is not None:
                        try:
                            from agent.secret_scope import reset_secret_scope
                            reset_secret_scope(scope)
                        except Exception:
                            pass

            @app.get("/")
            def phone_page() -> Any:
                return HTMLResponse(_mobile_html())

            app.include_router(router, prefix="/api")

            # Bind explicitly so a port already taken by a previous gateway
            # process fails loudly instead of silently serving stale code.
            import socket as _socket
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as probe:
                probe.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
                probe.bind(("0.0.0.0", MOBILE_PORT))
            server = uvicorn.Server(uvicorn.Config(
                app, host="0.0.0.0", port=MOBILE_PORT, log_level="error",
                access_log=False, lifespan="off",
            ))
            threading.Thread(target=server.run, name="ccp-mobile", daemon=True).start()
            _mobile_state["port"] = MOBILE_PORT
        except Exception:
            _mobile_state["port"] = None


_QR_ERR = ""


def _mobile_qr_dataurl(url: str) -> str:
    """Base64 PNG of a QR for the phone URL, so re-pairing after an IP change
    is one scan. Returns '' when segno is unavailable — the panel then just
    falls back to the copyable link."""
    global _QR_ERR
    _QR_ERR = ""
    if not url:
        return ""
    try:
        import io

        import segno  # optional dependency
    except Exception as exc:  # noqa: BLE001
        # The gateway rewrites sys.path for its vendored deps, so the
        # interpreter's own site-packages can drop off the path. Put it back
        # once and retry before giving up.
        try:
            import site as _site
            import sys as _sys

            for base in (getattr(_sys, "base_prefix", ""), getattr(_sys, "prefix", "")):
                if not base:
                    continue
                d = os.path.join(base, "Lib", "site-packages")
                if os.path.isdir(d):
                    _site.addsitedir(d)
            import segno  # type: ignore[no-redef]
        except Exception as exc2:  # noqa: BLE001
            _QR_ERR = "import: " + repr(exc2)[:160]
            return ""
    try:
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="png", scale=6, border=3,
                                        dark="#1F1D1B", light="#FFFFFF")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:  # noqa: BLE001
        _QR_ERR = "encode: " + repr(exc)[:160]
        return ""


@router.get("/mobile")
def mobile_info(request: Request) -> dict:
    """Address + token for the phone client (shown inside the panel)."""
    urls = _mobile_urls()
    qr = _mobile_qr_dataurl(urls[0] if urls else "")
    return _tr_obj({
        "ok": bool(_mobile_state.get("port")),
        "port": _mobile_state.get("port"),
        "token": _mobile_state.get("token"),
        "urls": urls,
        "url": urls[0] if urls else "",
        "qr": qr,
        "qr_error": ("" if qr else _QR_ERR),
        "hint": ("手机与电脑连同一个 Wi-Fi，用浏览器打开上面的链接，或直接扫码。"
                 "口令是固定的，只有 IP 会随重启变化——变了就回来再扫一次。"),
    }, _lang(request))


@router.get("/relay")
def relay_info() -> dict:
    """Where the panel can reach this process directly (never leaves loopback)."""
    return {"ok": True, "port": _relay_state["port"], "ports": list(RELAY_PORTS),
            "token": RELAY_TOKEN, "relay": bool(_relay_state["port"])}


_start_relay()
_start_mobile()
