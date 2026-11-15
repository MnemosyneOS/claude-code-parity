/**
 * Claude Code Desktop — Hermes Desktop front-end plugin.
 *
 * A graphical, non-terminal Claude Code workspace with the full local CLI
 * surface wired in: 107 settings (CLI flags + settings.json keys), attachments,
 * one-click upgrade, a real thinking/tool chain, in-plugin permission approvals,
 * a schema-driven settings page, persistent sessions, and the Claude brand palette.
 *
 * Constraints: plain uncompiled ESM, no JSX syntax, imports limited to
 * '@hermes/plugin-sdk', 'react', 'react/jsx-runtime'. All backend I/O goes
 * through ctx.rest (the /api/plugins/claude-code-parity namespace).
 */

import { cloneElement, isValidElement, useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import {
  atom,
  host,
  useValue,
  PANES_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  PALETTE_AREA,
  KEYBINDS_AREA
} from '@hermes/plugin-sdk'

/* ------------------------------------------------------------------ */
/* i18n — English / 中文                                                */
/*                                                                     */
/* Every user-visible string in this bundle is written in Chinese in   */
/* the source. `tr()` maps it to the active language at render time,   */
/* so switching language never means editing a call site. The JSX      */
/* factory `h()` below translates string children plus the purely      */
/* presentational text props (title / placeholder / aria-label) as     */
/* elements are created — the whole UI therefore follows `langAtom`    */
/* without per-string wiring.                                          */
/*                                                                     */
/* Strings assembled by the caller (`Running · ${n}`) cannot be looked */
/* up by key, so EN_TPL keeps one regex per interpolated template;     */
/* captured groups are translated recursively, which is what keeps     */
/* nested labels (a permission-mode name, a provider name) in the      */
/* active language too.                                                */
/*                                                                     */
/* Adding a language: extend LANGS, add its pack, and translate the    */
/* literals you want covered. A missing key falls back to the source   */
/* string, never to a blank.                                           */
/* ------------------------------------------------------------------ */
const LANG_STORAGE_KEY = 'ccp.lang'
const LANGS = ['en', 'zh']

/* Chinese source string → English. One entry per literal in this file. */
const EN = {
  "附件": "Attachments",
  "发送": "Send",
  "网关": "Gateway",
  "本机直连端口不可达": "Local direct port unreachable",
  "插件上下文未就绪": "Plugin context not ready",
  "直连": "Direct",
  "新建会话": "New Session",
  "正在连接 Hermes…": "Connecting to Hermes…",
  "模型与推理": "Model & Reasoning",
  "接受编辑": "Accept Edits",
  "自动": "Auto",
  "手动": "Manual",
  "计划": "Plan",
  "不询问": "Don't Ask",
  "绕过权限": "Bypass Permissions",
  "运行中 · ": "Running · ",
  "工具返回 · ": "Tool result · ",
  "请求失败": "Request failed",
  "等待审批 · ": "Awaiting approval · ",
  "工具调用": "Tool call",
  "审批超时自动拒绝": "Approval timed out, auto-denied",
  "已拒绝": "Denied",
  "始终允许": "Always Allow",
  "已允许": "Allowed",
  "错误": "Error",
  "就绪": "Ready",
  "错误 · ": "Error · ",
  "轮询失败 · ": "Polling failed · ",
  "设置保存失败 · ": "Failed to save settings · ",
  "审批已开启 · 工具调用会在插件内弹窗询问": "Approval on · tool calls prompt inside the plugin",
  "审批已关闭 · 需要授权的工具将被直接拒绝": "Approval off · tools that need authorization are denied outright",
  "当前没有待审批的操作": "No operations awaiting approval",
  "已拒绝该工具调用": "Denied this tool call",
  "已批准该工具调用": "Approved this tool call",
  "审批提交失败 · ": "Failed to submit approval · ",
  "后端未挂载（404）：当前工作区 profile 没有启用该插件的 Python 后端。请在 `profiles/<工作区>/config.yaml` 的 `plugins.enabled` 中加入 claude-code-parity，然后重试。": "Backend not mounted (404): the current workspace profile does not enable this plugin's Python backend. Add claude-code-parity to `plugins.enabled` in `profiles/<workspace>/config.yaml`, then retry.",
  "没有权限访问插件后端（401/403）：请重新登录 Hermes Desktop 或检查会话凭据。": "No permission to access the plugin backend (401/403): sign in to Hermes Desktop again or check the session credentials.",
  "连不上 Hermes 后端：请确认 Hermes Desktop / Gateway 正在运行，然后重试。": "Can't reach the Hermes backend: make sure Hermes Desktop / Gateway is running, then retry.",
  "Claude Code 安装损坏 · 可在「设置 → 升级与诊断」修复": "Claude Code installation damaged · fix it in Settings → Upgrade & Diagnostics",
  "正在连接插件后端…（重试 ": "Connecting to plugin backend… (retry ",
  "后端不可达 · 点击重试": "Backend unreachable · click to retry",
  "请在输入框右下角选择一个模型": "Choose a model at the bottom right of the input box",
  "（附件）": "(attachment)",
  "启动 Claude Code…": "Starting Claude Code…",
  "发送失败": "Failed to send",
  "发送失败: ": "Failed to send: ",
  "已停止": "Stopped",
  "会话已清空": "Session cleared",
  "刚刚": "Just now",
  " 分钟前": " min ago",
  " 小时前": " hr ago",
  " 天前": " d ago",
  "正在读取历史会话…": "Reading history…",
  "历史会话": "History",
  "已载入历史会话 · 继续发送会接着原会话": "History loaded · sending again continues the original session",
  "历史会话读取失败：": "Failed to read history: ",
  "已重命名": "Renamed",
  "已恢复自动标题": "Auto title restored",
  "重命名失败：": "Rename failed: ",
  "已归档 · 可在「已归档」里恢复": "Archived · restore it from Archived",
  "已取消归档": "Unarchived",
  "归档失败：": "Archive failed: ",
  "已移入回收站 · 可在「回收站」恢复或彻底删除": "Moved to Trash · restore or delete permanently from Trash",
  "删除失败：": "Delete failed: ",
  "已从回收站恢复": "Restored from Trash",
  "恢复失败：": "Restore failed: ",
  "已彻底删除 ": "Permanently deleted ",
  " 个会话": " conversations",
  "彻底删除失败：": "Permanent delete failed: ",
  "操作失败：": "Operation failed: ",
  "已复制会话 ID · 终端可用 claude --resume ": "Session ID copied · run claude --resume in a terminal ",
  "分支 · ": "Branch · ",
  "已创建分支 · 下一句话会从原会话分叉（--fork-session）": "Branch created · the next message forks from the original session (--fork-session)",
  "已移动到 ": "Moved to ",
  "移动失败：": "Move failed: ",
  "已在新控制台运行 claude --resume（": "Launched claude --resume in a new console (",
  "打开终端失败：": "Failed to open terminal: ",
  "已导出 Markdown · ": "Exported Markdown · ",
  "已导出并复制路径 · ": "Exported and copied path · ",
  "导出失败：": "Export failed: ",
  "已在新标签页打开 Claude Code": "Opened Claude Code in a new tab",
  "已打开 Claude Code 官方文档": "Opened the official Claude Code docs",
  "文档地址：docs.claude.com/en/docs/claude-code/overview": "Docs: docs.claude.com/en/docs/claude-code/overview",
  "正在上传附件…": "Uploading attachments…",
  "附件失败 · ": "Attachment failed · ",
  "正在保存设置…": "Saving settings…",
  "设置已保存 · 下一条消息生效": "Settings saved · applied to the next message",
  "保存失败 · ": "Failed to save · ",
  "已恢复默认设置": "Default settings restored",
  "恢复失败 · ": "Restore failed · ",
  "正在检查 Claude Code 更新…": "Checking for Claude Code updates…",
  "检查更新失败（可能是网络不可达）": "Update check failed (network may be unreachable)",
  "升级未完成 · ": "Upgrade incomplete · ",
  "升级结束（查看日志）": "Upgrade finished (see logs)",
  "升级状态查询失败": "Failed to query upgrade status",
  "正在升级 Claude Code…": "Upgrading Claude Code…",
  "升级启动失败 · ": "Failed to start upgrade · ",
  "图片 · ": "Image · ",
  "视频 · ": "Video · ",
  "文件 · ": "File · ",
  "正在思考…": "Thinking…",
  "思考过程": "Thought process",
  " 字": " chars",
  "已完成": "Done",
  "执行中": "Running",
  "调用": "Call",
  "收起": "Collapse",
  "详情": "Details",
  "(无参数)": "(no arguments)",
  "思考": "Thinking",
  "工具返回": "Tool result",
  "用量": "Usage",
  "日志": "Logs",
  "节点": "Node",
  "异常结束": "Failed",
  "进行中": "Running",
  "本轮没有产生上游思考或工具调用事件。": "This turn produced no upstream thinking or tool call events.",
  "选择模型": "Select Model",
  "● 在线": "● Online",
  "探测通过 · HTTP 200": "Probe passed · HTTP 200",
  "○ 未探测": "○ Not probed",
  "未执行在线探测": "Online probe not run",
  "○ 离线": "○ Offline",
  "○ 需积分": "○ Needs credits",
  "○ 模型名不兼容": "○ Incompatible model name",
  "○ 凭据无效": "○ Invalid credentials",
  "○ 服务未启动": "○ Service not running",
  "在线探测未通过": "Online probe failed",
  "模型已切换 · ": "Model switched · ",
  "选择模型 · Hermes Desktop 中全部 ": "Select model · all ",
  " 个模型": " models in Hermes Desktop",
  "选择模型 · Hermes Desktop": "Select model · Hermes Desktop",
  "搜索模型或提供商…": "Search models or providers…",
  " 个": " models",
  "没有匹配的模型，试试其他关键词。": "No matching models. Try a different keyword.",
  "状态为组级探测（每组仅试 1 个模型），仅供参考；标记异常仍可选择": "Status comes from a group-level probe (one model tried per group); for reference only — flagged models can still be selected",
  "新会话": "New Session",
  "当前模型 · 点击切换": "Current model · click to switch",
  "有待审批的操作，点此允许第一个（Y）": "Operations awaiting approval, click to allow the first (Y)",
  "更多会话参数（工具 / 强度 / 视图 / 权限 / 目录 / 审批开关）": "More session options (tools / effort / view / permission / directory / approval)",
  "更多": "More",
  "重新读取 Hermes 模型目录": "Reload the Hermes model catalog",
  "刷新": "Refresh",
  "打开插件设置（CLI 全量配置 / 升级 / 功能矩阵）": "Open plugin settings (full CLI config / upgrade / capability matrix)",
  "设置": "Settings",
  "升级与诊断": "Upgrade & Diagnostics",
  "升级中…": "Upgrading…",
  "升级": "Upgrade",
  "目录": "Dir",
  "Claude Code 的工作目录": "Claude Code working directory",
  "工具调用方式": "Tool call mode",
  "工具·自动": "Tools·Auto",
  "工具·仅描述": "Tools·Describe only",
  "工具·关闭": "Tools·Off",
  "推理强度": "Reasoning effort",
  "强度·默认": "Effort·Default",
  "低": "Low",
  "中": "Medium",
  "高": "High",
  "极高": "Extra high",
  "最大": "Max",
  "消息显示详细程度": "Message verbosity",
  "标准视图": "Standard view",
  "详细视图": "Verbose view",
  "精简视图": "Compact view",
  "权限模式 · 输入框 Shift+Tab 循环切换 · ⌘/Ctrl+Shift+P": "Permission mode · Shift+Tab in the input box to cycle · ⌘/Ctrl+Shift+P",
  "权限·": "Permission·",
  "插件内审批开关 · ⌘/Ctrl+Shift+B": "In-plugin approval toggle · ⌘/Ctrl+Shift+B",
  "审批·开": "Approval·On",
  "审批·关": "Approval·Off",
  "授权请求 · Claude Code": "Authorization request · Claude Code",
  "未知工具": "Unknown tool",
  "✓ 允许  Y": "✓ Allow  Y",
  "✓✓ 始终允许  A": "✓✓ Always allow  A",
  "✕ 拒绝  N": "✕ Deny  N",
  "Esc 拒绝": "Esc to deny",
  "工作目录": "Working directory",
  "移除附件": "Remove attachment",
  "回复…": "Reply…",
  "上传附件（图片、视频、文件）": "Upload attachments (images, videos, files)",
  "停止生成（Esc）": "Stop generating (Esc)",
  "停止": "Stop",
  "发送（Enter）": "Send (Enter)",
  "会话名称（留空恢复自动标题）": "Session name (leave empty to restore the auto title)",
  "恢复 Claude 自动生成的标题": "Restore Claude's auto-generated title",
  "未命名会话": "Untitled session",
  " 轮": " turns",
  "未读": "Unread",
  "重命名 / 归档 / 删除": "Rename / Archive / Delete",
  "没有会话": "No sessions",
  "＋ 新建会话": "＋ New Session",
  "搜索会话…": "Search sessions…",
  "会话": "Sessions",
  "已归档": "Archived",
  "回收站": "Trash",
  "已归档会话": "Archived sessions",
  "Claude Code 历史会话": "Claude Code history",
  "读取中…": "Reading…",
  "重新扫描 ~/.claude/projects": "Rescan ~/.claude/projects",
  "删除于 ": "Deleted on ",
  "恢复到原项目": "Restore to original project",
  "恢复": "Restore",
  "彻底删除，不可恢复": "Delete permanently, cannot be undone",
  "确认": "Confirm",
  "删除": "Delete",
  "再次点击确认清空回收站": "Click again to empty Trash",
  "清空回收站": "Empty Trash",
  "回收站是空的": "Trash is empty",
  "当前会话": "Current session",
  "从列表移除（不删除 CLI 历史）": "Remove from list (keeps CLI history)",
  "已归档 · 点击恢复": "Archived · click to restore",
  "历史会话 · ": "History · ",
  "载入": "Load",
  "没有归档的会话": "No archived sessions",
  "这个项目还没有历史会话": "This project has no history yet",
  "点击「载入」读取 CLI 历史": "Click Load to read CLI history",
  "● Claude Code 已就绪": "● Claude Code ready",
  "● 已连接 · CLI 安装损坏": "● Connected · CLI installation damaged",
  "○ 后端未连接": "○ Backend not connected",
  "安装需修复（设置 → 升级与诊断）": "Installation needs repair (Settings → Upgrade & Diagnostics)",
  "后端未就绪 · 见主区域": "Backend not ready · see main area",
  "用手机在同一 Wi-Fi 下打开同样的界面": "Open the same UI on your phone over the same Wi-Fi",
  "手机访问": "Phone access",
  "来自 Claude Code 历史记录 · ": "From Claude Code history · ",
  " · 继续发送会接着这个会话（--resume），不会新建": " · sending again continues this session (--resume) instead of starting a new one",
  "插件后端未就绪": "Plugin backend not ready",
  "原始错误：": "Original error: ",
  "重新连接": "Reconnect",
  "自动尝试过的通道：网关插件接口 → 本机直连（127.0.0.1:47823~47828）。": "Channels tried automatically: gateway plugin API → local direct connect (127.0.0.1:47823~47828).",
  "当前通道：": "Current channel: ",
  "打开会话": "Open Session",
  "在新标签页中打开": "Open in New Tab",
  "在终端中打开": "Open in Terminal",
  "重命名…": "Rename…",
  "取消置顶": "Unpin",
  "置顶": "Pin to Top",
  "已取消置顶": "Unpinned",
  "已置顶": "Pinned",
  "标记为已读": "Mark as Read",
  "标记为未读": "Mark as Unread",
  "已标记为已读": "Marked as read",
  "已标记为未读": "Marked as unread",
  "复制 ID": "Copy ID",
  "分支（新建会话）": "Branch (new session)",
  "导出为 Markdown": "Export as Markdown",
  "移动到项目 ›": "Move to Project ›",
  "外观": "Appearance",
  "外观与界面": "Appearance & Interface",
  "帮助": "Help",
  "取消归档": "Unarchive",
  "归档": "Archive",
  "再次点击确认删除": "Click again to confirm delete",
  "删除（移到回收站）": "Delete (move to Trash)",
  "没有其它项目": "No other projects",
  "手机访问 Claude Code": "Phone Access to Claude Code",
  "手机与电脑连同一个 Wi-Fi，用浏览器打开下面的链接。": "Connect your phone and computer to the same Wi-Fi, then open the link below in a browser.",
  "正在读取局域网地址…": "Reading LAN address…",
  "手机访问二维码": "Phone access QR code",
  "手机相机扫一下即可进入": "Scan it with your phone camera to open",
  "已复制手机访问链接": "Phone access link copied",
  "复制": "Copy",
  "没有检测到局域网地址。请确认电脑已连 Wi-Fi/网线，或检查 47830 端口是否被占用。": "No LAN address detected. Make sure the computer is on Wi-Fi/Ethernet, or check whether port 47830 is in use.",
  "访问口令是固定的，重启电脑也不会变；会变的只是前面的 IP。": "The access code is fixed and survives reboots; only the IP prefix changes.",
  "想让 IP 也不变：登录路由器（通常是 192.168.1.1）给这台电脑做「DHCP 地址保留 / 静态分配」。": "To keep the IP fixed too: sign in to your router (usually 192.168.1.1) and set a DHCP reservation / static assignment for this computer.",
  "手机端可直接点「允许 / 拒绝」完成工具审批，不用再回电脑。": "You can approve tools right from your phone with Allow / Deny — no need to go back to the computer.",
  "手机打不开时，先确认同一 Wi-Fi，再看 Windows 防火墙是否放行入站 47830。": "If the phone can't open it, confirm the same Wi-Fi first, then check that Windows Firewall allows inbound 47830.",
  "关闭": "Close",
  "未选模型": "No model selected",
  "CLI 功能矩阵": "CLI Capability Matrix",
  "开启": "On",
  "（默认 / 留空）": "(default / empty)",
  "JSON 对象或纯文本…": "JSON object or plain text…",
  "每行一项，或用逗号分隔": "One per line, or comma-separated",
  "Claude Code 升级与诊断": "Claude Code Upgrade & Diagnostics",
  "直接调用本机 npm / claude update，升级后自动复核版本并刷新 CLI 能力清单。": "Runs npm / claude update locally, then re-checks the version and refreshes the CLI capability list.",
  "当前版本：": "Current version: ",
  "未知": "Unknown",
  "最新版本：": "Latest version: ",
  "未获取到": "Not fetched",
  "未检查": "Not checked",
  "安装目录：": "Install directory: ",
  "CLI 可执行文件：": "CLI executable: ",
  "安装状态：正常（原生二进制已就位）": "Install status: OK (native binary in place)",
  "安装状态：损坏 · ": "Install status: damaged · ",
  "原生二进制缺失": "native binary missing",
  "检测到可用更新，点击「一键升级」即可安装。": "An update is available — click One-Click Upgrade to install it.",
  "本地为 npm 依赖安装，升级执行 npm install @anthropic-ai/claude-code@latest。": "The local install is an npm dependency; upgrading runs npm install @anthropic-ai/claude-code@latest.",
  "检查更新": "Check for Updates",
  "升级进行中…": "Upgrading…",
  "一键升级（npm）": "One-Click Upgrade (npm)",
  "用 claude update": "Use claude update",
  "不联网重装，只补跑原生二进制安装脚本并校验": "Reinstall offline — only re-runs the native binary install script and verifies it",
  "修复安装": "Repair Installation",
  "错误：": "Error: ",
  "退出码 ": "Exit code ",
  " · 新版本 ": " · new version ",
  "升级日志": "Upgrade log",
  "（暂无日志）": "(no logs yet)",
  "本机 CLI 概况": "Local CLI overview",
  "CLI 帮助输出来自本机 claude.exe --help，非文档臆测。": "CLI help output comes from the local claude.exe --help, not from doc guesswork.",
  "已配置": "Configured",
  "部分": "Partial",
  "架构受限": "Architecture-limited",
  "CLI 功能矩阵与配置映射": "CLI Capability Matrix & Config Mapping",
  "逐项对照本机 Claude Code 2.1.322。「架构受限」是 headless 单轮执行 + 协议桥的固有限制，不是配置缺失。": "Compared item by item against the local Claude Code 2.1.322. “Architecture-limited” means an inherent limit of headless single-turn execution + the protocol bridge, not a missing configuration.",
  "能力": "Capability",
  "状态": "Status",
  "实现方式 / 限制": "Implementation / Limits",
  "Slash 命令": "Slash commands",
  "配置尚未载入": "Configuration not loaded yet",
  "全量设置尚未载入": "Full settings not loaded yet",
  "正在从插件后端读取配置架构（107 项）…": "Reading config schema from the plugin backend (107 items)…",
  "重新读取": "Reload",
  "设置持久化到插件 .runtime/plugin-settings.json，不修改 ~/.claude/settings.json。": "Settings persist to the plugin's .runtime/plugin-settings.json; ~/.claude/settings.json is not modified.",
  "每项都标注了对应的 CLI flag 或 settings.json 键。保存后由后端生成单会话 settings.json 与完整命令行参数，下一条消息生效。": "Each item is annotated with its matching CLI flag or settings.json key. After saving, the backend generates a per-session settings.json and the full command line, applied on the next message.",
  "保存设置 *": "Save Settings *",
  "保存设置": "Save Settings",
  "恢复默认": "Restore Defaults",
  "有未保存的修改": "Unsaved changes",
  "已与后端同步": "In sync with backend",
  "审批方式：": "Approval mode: ",
  "插件内弹窗（host）": "In-plugin dialog (host)",
  "关闭（none）": "Off (none)",
  " · 权限模式：": " · permission mode: ",
  "开启后 CLI 通过 --permission-prompt-tool 把授权请求交给插件；卡片支持 Y 允许 / A 始终允许 / N 拒绝 / Esc 拒绝，超时自动拒绝。": "When enabled, the CLI hands authorization requests to the plugin via --permission-prompt-tool; the card supports Y allow / A always allow / N deny / Esc deny, with auto-deny on timeout.",
  "快捷键：输入框内 Shift+Tab 或 ⌘/Ctrl+Shift+P 循环权限模式 · ⌘/Ctrl+Shift+B 开关审批 · ⌘/Ctrl+Shift+Y / N / J 允许 / 拒绝 / 始终允许。": "Shortcuts: Shift+Tab or ⌘/Ctrl+Shift+P in the input box cycles permission modes · ⌘/Ctrl+Shift+B toggles approval · ⌘/Ctrl+Shift+Y / N / J allow / deny / always allow.",
  "正在读取配置架构…": "Reading config schema…",
  "本机 Claude Code 的图形化工作区：全量 CLI 配置、附件、一键升级、插件内工具审批、思考链与全部 Hermes 模型。": "A graphical workspace for the local Claude Code: full CLI configuration, attachments, one-click upgrade, in-plugin tool approval, thinking chains and every Hermes model.",
  "Claude Code: 打开工作区": "Claude Code: Open Workspace",
  "Claude Code: 新建会话": "Claude Code: New Session",
  "Claude Code: 清空当前会话": "Claude Code: Clear Current Session",
  "Claude Code: 刷新 Hermes 模型目录": "Claude Code: Refresh Hermes Model Catalog",
  "Claude Code: 打开全量设置": "Claude Code: Open Full Settings",
  "Claude Code: 检查更新": "Claude Code: Check for Updates",
  "Claude Code: 一键升级": "Claude Code: One-Click Upgrade",
  "Claude Code: 查看 CLI 功能矩阵": "Claude Code: View CLI Capability Matrix",
  "Claude Code: 复制当前会话为 Markdown": "Claude Code: Copy Current Session as Markdown",
  "会话已复制到剪贴板": "Session copied to clipboard",
  "Claude Code: 在资源管理器中打开工作目录": "Claude Code: Open Working Directory in Explorer",
  "Claude Code: 切换思考过程显示": "Claude Code: Toggle Thinking Display",
  "思考过程显示：": "Thinking display: ",
  "Claude Code: 循环切换权限模式 (Shift+Tab)": "Claude Code: Cycle Permission Mode (Shift+Tab)",
  "Claude Code: 开关插件内工具审批": "Claude Code: Toggle In-Plugin Tool Approval",
  "Claude Code: 允许当前审批": "Claude Code: Allow Current Approval",
  "Claude Code: 始终允许当前工具": "Claude Code: Always Allow Current Tool",
  "Claude Code: 拒绝当前审批": "Claude Code: Deny Current Approval",
  "Claude Code: 循环切换权限模式（同终端 Shift+Tab）": "Claude Code: Cycle Permission Mode (same as Shift+Tab in the terminal)",
  "Claude Code: 允许当前审批 (Y)": "Claude Code: Allow Current Approval (Y)",
  "Claude Code: 始终允许当前工具 (A)": "Claude Code: Always Allow Current Tool (A)",
  "Claude Code: 拒绝当前审批 (N)": "Claude Code: Deny Current Approval (N)",
}

/* Interpolated templates, matched after the caller fills them in. */
const EN_TPL = [
  [new RegExp("^已复制会话 ID · 终端可用 claude --resume (.*)$"), "Session ID copied · run claude --resume in a terminal $1"],  // 已复制会话 ID · 终端可用 claude -
  [new RegExp("^思考链 · (.*?) 字思考 · (.*?) 次工具调用 · (.*?) 次返回 · (.*?)s$"), "Thinking trace · $1 chars of thinking · $2 tool calls · $3 results · $4s"],  // 思考链 · ${chars} 字思考 · ${t
  [new RegExp("^(.*) · 继续发送会接着这个会话（--resume），不会新建$"), "$1 · sending again continues this session (--resume) instead of starting a new one"],  //  · 继续发送会接着这个会话（--resume）
  [new RegExp("^权限模式 → (.*?)（(.*?)）· Shift\\+Tab 继续切换$"), "Permission mode → $1 ($2) · Shift+Tab to cycle"],  // 权限模式 → ${next}（${PERMISS
  [new RegExp("^选择模型 · Hermes Desktop 中全部 (.*)$"), "Select model · all $1"],  // 选择模型 · Hermes Desktop 中全
  [new RegExp("^已在新控制台运行 claude --resume（(.*)$"), "Launched claude --resume in a new console ($1"],  // 已在新控制台运行 claude --resume
  [new RegExp("^已映射 settings\\.json 键（(.*?)）$"), "Mapped settings.json keys ($1)"],  // 已映射 settings.json 键（${cl
  [new RegExp("^来自 Claude Code 历史记录 · (.*)$"), "From Claude Code history · $1"],  // 来自 Claude Code 历史记录 · 
  [new RegExp("^思考结束 · (.*?) 字 · 上游工具调用 (.*?) 次$"), "Thinking done · $1 chars · $2 upstream tool calls"],  // 思考结束 · ${ev.chars || 0} 
  [new RegExp("^Claude Code (.*?) · 点击一键升级$"), "Claude Code $1 · click to upgrade"],  // Claude Code ${b.version 
  [new RegExp("^共 (.*?) 个模型 · 凭据来自 Hermes$"), "$1 models · credentials from Hermes"],  // 共 ${b.total || 0} 个模型 · 
  [new RegExp("^解析到 (.*?) 个 CLI flags · (.*)$"), "Parsed $1 CLI flags · $2"],  // 解析到 ${cli.flags?.length 
  [new RegExp("^(.*?) 个 settings\\.json 键$"), "$1 settings.json keys"],  // ${cli.mapped_settings_ke
  [new RegExp("^(.*?) 个 slash 命令（见功能矩阵）$"), "$1 slash commands (see feature matrix)"],  // ${cli.slash_commands?.le
  [new RegExp("^本机 CLI 全部 flags（(.*?)）$"), "All local CLI flags ($1)"],  // 本机 CLI 全部 flags（${cli.fl
  [new RegExp("^已映射 CLI flags（(.*?)）$"), "Mapped CLI flags ($1)"],  // 已映射 CLI flags（${cli.mapp
  [new RegExp("^已导出 Markdown · (.*)$"), "Exported Markdown · $1"],  // 已导出 Markdown · 
  [new RegExp("^CC · (.*?) · (.*?) 模型 · (.*?)$"), "CC · $1 · $2 models · $3"],  // CC · ${label} · ${b.tota
  [new RegExp("^(.*?) 个 settings 键$"), "$1 settings keys"],  // ${cli.mapped_settings_ke
  [new RegExp("^正在连接插件后端…（重试 (.*)$"), "Connecting to plugin backend… (retry $1"],  // 正在连接插件后端…（重试 
  [new RegExp("^另有 (.*?) 个操作等待审批…$"), "$1 more operations awaiting approval…"],  // 另有 ${list.length - 2} 个操
  [new RegExp("^(.*?) 个已映射到设置项 · (.*)$"), "$1 mapped to settings · $2"],  // ${cli.mapped_flags?.leng
  [new RegExp("^(.*?) 个 CLI flags$"), "$1 CLI flags"],  // ${cli.mapped_flags?.leng
  [new RegExp("^已导出并复制路径 · (.*)$"), "Exported and copied path · $1"],  // 已导出并复制路径 · 
  [new RegExp("^安装状态：损坏 · (.*)$"), "Install status: damaged · $1"],  // 安装状态：损坏 · 
  [new RegExp("^权限审批请求 → (.*?)$"), "Approval request → $1"],  // 权限审批请求 → ${ev.tool_name 
  [new RegExp("^已是最新版本 · (.*?)$"), "Up to date · $1"],  // 已是最新版本 · ${r.current}
  [new RegExp("^⏱ (.*?)s 后自动拒绝$"), "⏱ auto-deny in $1s"],  // ⏱ ${left}s 后自动拒绝
  [new RegExp("^设置保存失败 · (.*)$"), "Failed to save settings · $1"],  // 设置保存失败 · 
  [new RegExp("^审批提交失败 · (.*)$"), "Failed to submit approval · $1"],  // 审批提交失败 · 
  [new RegExp("^历史会话读取失败：(.*)$"), "Failed to read history: $1"],  // 历史会话读取失败：
  [new RegExp("^升级启动失败 · (.*)$"), "Failed to start upgrade · $1"],  // 升级启动失败 · 
  [new RegExp("^权限审批 (.*?) · (.*?)$"), "Approval $1 · $2"],  // 权限审批 ${label} · ${ev.too
  [new RegExp("^(.*?) \\/ (.*?) 待审批$"), "$1 / $2 pending"],  // ${i + 1} / ${list.length
  [new RegExp("^(.*?) 个子命令 · (.*)$"), "$1 subcommands · $2"],  // ${cli.subcommands?.lengt
  [new RegExp("^升级未完成 · (.*)$"), "Upgrade incomplete · $1"],  // 升级未完成 · 
  [new RegExp("^模型已切换 · (.*)$"), "Model switched · $1"],  // 模型已切换 · 
  [new RegExp("^升级完成 · (.*?)$"), "Upgrade complete · $1"],  // 升级完成 · ${r.after || ''}
  [new RegExp("^(.*?) · (.*?) 个模型$"), "$1 · $2 models"],  // ${st} · ${b.total || 0} 
  [new RegExp("^工具返回 · (.*)$"), "Tool result · $1"],  // 工具返回 · 
  [new RegExp("^等待审批 · (.*)$"), "Awaiting approval · $1"],  // 等待审批 · 
  [new RegExp("^轮询失败 · (.*)$"), "Polling failed · $1"],  // 轮询失败 · 
  [new RegExp("^彻底删除失败：(.*)$"), "Permanent delete failed: $1"],  // 彻底删除失败：
  [new RegExp("^打开终端失败：(.*)$"), "Failed to open terminal: $1"],  // 打开终端失败：
  [new RegExp("^附件失败 · (.*)$"), "Attachment failed · $1"],  // 附件失败 · 
  [new RegExp("^保存失败 · (.*)$"), "Failed to save · $1"],  // 保存失败 · 
  [new RegExp("^恢复失败 · (.*)$"), "Restore failed · $1"],  // 恢复失败 · 
  [new RegExp("^历史会话 · (.*)$"), "History · $1"],  // 历史会话 · 
  [new RegExp("^ · 新版本 (.*)$"), " · new version $1"],  //  · 新版本 
  [new RegExp("^思考过程显示：(.*)$"), "Thinking display: $1"],  // 思考过程显示：
  [new RegExp("^有更新 · (.*?)$"), "Update available · $1"],  // 有更新 · ${r.latest}
  [new RegExp("^共 (.*?) 项配置$"), "$1 settings in total"],  // 共 ${schema.length} 项配置
  [new RegExp("^运行中 · (.*)$"), "Running · $1"],  // 运行中 · 
  [new RegExp("^发送失败: (.*)$"), "Failed to send: $1"],  // 发送失败: 
  [new RegExp("^重命名失败：(.*)$"), "Rename failed: $1"],  // 重命名失败：
  [new RegExp("^已彻底删除 (.*)$"), "Permanently deleted $1"],  // 已彻底删除 
  [new RegExp("^错误 · (.*)$"), "Error · $1"],  // 错误 · 
  [new RegExp("^归档失败：(.*)$"), "Archive failed: $1"],  // 归档失败：
  [new RegExp("^删除失败：(.*)$"), "Delete failed: $1"],  // 删除失败：
  [new RegExp("^恢复失败：(.*)$"), "Restore failed: $1"],  // 恢复失败：
  [new RegExp("^操作失败：(.*)$"), "Operation failed: $1"],  // 操作失败：
  [new RegExp("^分支 · (.*)$"), "Branch · $1"],  // 分支 · 
  [new RegExp("^已移动到 (.*)$"), "Moved to $1"],  // 已移动到 
  [new RegExp("^移动失败：(.*)$"), "Move failed: $1"],  // 移动失败：
  [new RegExp("^导出失败：(.*)$"), "Export failed: $1"],  // 导出失败：
  [new RegExp("^原始错误：(.*)$"), "Original error: $1"],  // 原始错误：
  [new RegExp("^当前通道：(.*)$"), "Current channel: $1"],  // 当前通道：
  [new RegExp("^待审批 (.*?)$"), "$1 pending"],  // 待审批 ${pending.length}
  [new RegExp("^删除于 (.*)$"), "Deleted on $1"],  // 删除于 
  [new RegExp("^退出码 (.*)$"), "Exit code $1"],  // 退出码 
  [new RegExp("^(.*) 分钟前$"), "$1 min ago"],  //  分钟前
  [new RegExp("^(.*) 小时前$"), "$1 hr ago"],  //  小时前
  [new RegExp("^(.*) 个会话$"), "$1 conversations"],  //  个会话
  [new RegExp("^(.*) 个模型$"), "$1 models in Hermes Desktop"],  //  个模型
  [new RegExp("^权限·(.*)$"), "Permission·$1"],  // 权限·
  [new RegExp("^错误：(.*)$"), "Error: $1"],  // 错误：
  [new RegExp("^(.*) 天前$"), "$1 d ago"],  //  天前
  [new RegExp("^(.*) 字$"), "$1 chars"],  //  字
  [new RegExp("^(.*) 个$"), "$1 models"],  //  个
  [new RegExp("^(.*) 轮$"), "$1 turns"],  //  轮
]

function readLang() {
  try {
    const saved = window.localStorage.getItem(LANG_STORAGE_KEY)
    if (LANGS.indexOf(saved) >= 0) return saved
  } catch (_) { /* storage can be unavailable; fall through to the locale */ }
  try {
    const nav = String((navigator && navigator.language) || '').toLowerCase()
    return nav.indexOf('zh') === 0 ? 'zh' : 'en'
  } catch (_) { return 'en' }
}

const langAtom = atom(readLang())

function setLang(next) {
  if (LANGS.indexOf(next) < 0) return
  try { window.localStorage.setItem(LANG_STORAGE_KEY, next) } catch (_) { /* ignore */ }
  langAtom.set(next)
}

/* Fullwidth punctuation surviving inside an otherwise translated string reads
   as a typo in English. Normalise it once, on output that really was
   translated — untranslated user text is never touched. */
const EN_PUNCT = {
  '（': '(', '）': ')', '：': ': ', '；': '; ', '，': ', ',
  '。': '.', '！': '!', '？': '?', '、': ', '
}

function polishEn(text) {
  return text.replace(/[（）：；，。！？、]/g, (c) => (EN_PUNCT[c] !== undefined ? EN_PUNCT[c] : c))
}

/** One rewrite pass: whole-string dictionary hit, then the pattern table. */
function translateOnce(value) {
  const hit = EN[value]
  if (hit !== undefined) return polishEn(hit)
  for (let i = 0; i < EN_TPL.length; i += 1) {
    const m = EN_TPL[i][0].exec(value)
    if (m) {
      return polishEn(EN_TPL[i][1].replace(/\$(\d)/g, (whole, n) => tr(m[Number(n)])))
    }
  }
  return value
}

/** Translate one finished string. Unknown strings pass through untouched.
    Several passes because a string the caller built by joining fragments gets
    translated one fragment at a time; every pattern needs Chinese to fire, so
    the loop settles instead of oscillating. */
function tr(value) {
  if (typeof value !== 'string' || !value) return value
  if (langAtom.get() === 'zh') return value
  let out = value
  for (let pass = 0; pass < 4; pass += 1) {
    const next = translateOnce(out)
    if (next === out) break
    out = next
  }
  return out
}

/** Props that only ever hold display text. `value` / `data` are never touched. */
const TEXT_PROPS = ['title', 'placeholder', 'aria-label']

/** React's jsx runtime takes `key` as its 3rd argument. */
const h = (type, props, ...kids) => {
  const p = { ...(props || {}) }
  const key = p.key
  delete p.key
  for (let i = 0; i < TEXT_PROPS.length; i += 1) {
    const name = TEXT_PROPS[i]
    if (typeof p[name] === 'string') p[name] = tr(p[name])
  }
  if (kids.length === 1) {
    p.children = typeof kids[0] === 'string' ? tr(kids[0]) : kids[0]
  } else if (kids.length) {
    p.children = kids.map((kid, i) => {
      if (typeof kid === 'string') return tr(kid)
      return isValidElement(kid) && kid.key == null ? cloneElement(kid, { key: 'k' + i }) : kid
    })
  }
  return key !== undefined && key !== null ? jsx(type, p, key) : jsx(type, p)
}

const PLUGIN_ID = 'claude-code-parity'

/* ------------------------------------------------------------------ */
/* Claude brand palette. Defaults to the official coral / warm-white look  */
/* instead of inheriting Hermes' purple accent.                          */
/* ------------------------------------------------------------------ */
const PALETTES = {
  claude: {
    bg: '#FAF9F5', bg2: '#F0EEE6', bg3: '#E7E3D8', text: '#1F1D1B',
    dim: '#5C5952', faint: '#8A867C', line: '#E6E2D7',
    accent: '#C96442', accent2: '#A34E32', red: '#BF4A3E',
    green: '#3E8E5A', bubble: '#F0EEE6', code: '#F4F1E9',
    white: '#FFFFFF', input: '#F5F4EF',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
  },
  'claude-dark': {
    bg: '#1C1B19', bg2: '#262420', bg3: '#322F2A', text: '#F3F0E9',
    dim: '#BDB8AD', faint: '#8E887C', line: '#3E3A34',
    accent: '#E08A66', accent2: '#C9714C', red: '#E5705F',
    green: '#6DBE8C', bubble: '#302D28', code: '#24221F',
    white: '#FFFFFF', input: '#232120',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
  },
  hermes: {
    bg: 'var(--ui-bg-primary, #fff)', bg2: 'var(--ui-bg-secondary, rgba(127,127,127,0.07))',
    bg3: 'var(--ui-bg-tertiary, rgba(127,127,127,0.14))',
    text: 'var(--ui-text-primary, #1b1b1b)', dim: 'var(--ui-text-secondary, rgba(127,127,127,0.95))',
    faint: 'var(--ui-text-tertiary, rgba(127,127,127,0.72))',
    line: 'var(--ui-stroke-secondary, rgba(127,127,127,0.25))',
    accent: '#D97757', accent2: '#B95738', red: '#e5534b',
    green: '#3fa66a', bubble: 'var(--ui-bg-tertiary, rgba(127,127,127,0.14))',
    code: 'var(--ui-bg-secondary, rgba(127,127,127,0.07))',
    white: '#FFFFFF',
    input: 'var(--ui-bg-secondary, rgba(127,127,127,0.06))',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
  }
}

const makeStyles = (P) => ({
  root: { position: 'relative', display: 'flex', height: '100%', minHeight: 0,
          width: '100%', overflow: 'hidden', background: P.bg, color: P.text,
          fontSize: '0.78rem' },
  side: { width: '238px', minWidth: '238px', display: 'flex', flexDirection: 'column',
          borderRight: `1px solid ${P.line}`, background: P.bg2 },
  sideTools: { padding: '7px 8px 2px' },
  histSearch: { width: '100%', boxSizing: 'border-box', padding: '5px 8px',
                borderRadius: '7px', border: `1px solid ${P.line}`, background: P.bg,
                color: P.text, fontSize: '0.7rem', outline: 'none', marginBottom: '6px' },
  histTabs: { display: 'flex', gap: '3px', marginBottom: '4px' },
  histTabBtn: { flex: 1, padding: '3px 0', borderRadius: '6px', cursor: 'pointer',
                border: `1px solid transparent`, background: 'transparent',
                color: P.faint, fontSize: '0.64rem' },
  histHead: { display: 'flex', alignItems: 'center', gap: '5px', padding: '3px 2px 2px',
              fontSize: '0.62rem', color: P.faint },
  miniBtn: { border: `1px solid ${P.line}`, background: P.bg, color: P.dim,
             borderRadius: '5px', fontSize: '0.62rem', padding: '2px 6px', cursor: 'pointer' },
  histSect: { display: 'flex', alignItems: 'center', gap: '4px', padding: '8px 6px 3px',
              fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.04em',
              color: P.faint, textTransform: 'uppercase' },
  hrow: { display: 'flex', alignItems: 'center', gap: '4px', padding: '5px 7px',
          borderRadius: '7px', cursor: 'pointer', marginBottom: '1px' },
  hrowTitle: { fontSize: '0.71rem', overflow: 'hidden', textOverflow: 'ellipsis',
               whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '3px' },
  hrowMeta: { fontSize: '0.61rem', color: P.faint, overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '1px' },
  hrowMenu: { border: 0, background: 'transparent', color: P.faint, cursor: 'pointer',
              fontSize: '0.8rem', lineHeight: 1, padding: '0 3px', transition: 'opacity .12s' },
  renameInput: { flex: 1, minWidth: 0, background: P.bg, color: P.text,
                 border: `1px solid ${P.accent}`, borderRadius: '6px',
                 fontSize: '0.7rem', padding: '3px 6px', outline: 'none' },
  modalWrap: { position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(31,29,27,0.30)',
               display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '18px' },
  modal: { width: '100%', maxWidth: '480px', maxHeight: '82vh', overflowY: 'auto',
           background: P.bg, border: `1px solid ${P.line}`, borderRadius: '14px',
           padding: '16px 16px 14px', boxShadow: '0 18px 50px rgba(0,0,0,0.28)' },
  urlRow: { display: 'flex', alignItems: 'center', gap: '6px', marginTop: '7px' },
  urlCode: { flex: 1, minWidth: 0, fontFamily: P.mono, fontSize: '0.66rem', color: P.text,
             background: P.bg2, border: `1px solid ${P.line}`, borderRadius: '7px',
             padding: '6px 8px', wordBreak: 'break-all', lineHeight: 1.5 },
  histBanner: { padding: '5px 14px', fontSize: '0.64rem', color: P.dim,
                background: P.bg2, borderBottom: `1px solid ${P.line}` },
  histEmpty: { fontSize: '0.66rem', color: P.faint, padding: '10px 8px', lineHeight: 1.6 },
  histErr: { fontSize: '0.64rem', color: P.red, padding: '6px 8px', lineHeight: 1.5,
             wordBreak: 'break-word' },
  menuOverlay: { position: 'fixed', inset: 0, zIndex: 70, background: 'transparent' },
  menu: { position: 'fixed', zIndex: 80, width: '214px', padding: '4px',
          display: 'flex', flexDirection: 'column', background: P.bg,
          border: `1px solid ${P.line}`, borderRadius: '10px',
          boxShadow: '0 12px 32px rgba(0,0,0,0.18)' },
  menuItem: { textAlign: 'left', border: 0, background: 'transparent', color: P.text,
              borderRadius: '6px', padding: '5px 9px', fontSize: '0.71rem',
              cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden',
              textOverflow: 'ellipsis' },
  menuSep: { height: '1px', background: P.line, margin: '4px 6px' },
  unreadDot: { width: '6px', height: '6px', borderRadius: '50%', background: P.accent,
               flexShrink: 0 },
  sideHead: { padding: '10px 10px 8px', display: 'flex', alignItems: 'center', gap: '7px',
              borderBottom: `1px solid ${P.line}` },
  sideList: { flex: 1, minHeight: 0, overflowY: 'auto', padding: '6px' },
  sideFoot: { padding: '8px 10px', borderTop: `1px solid ${P.line}`, fontSize: '0.66rem', color: P.faint },
  brand: { fontWeight: 650, fontSize: '0.8rem', letterSpacing: '-0.01em', flex: 1 },
  badge: { fontSize: '0.6rem', padding: '1px 5px', borderRadius: '9px',
           background: P.accent, color: P.white, fontWeight: 600 },
  newBtn: { width: '100%', padding: '6px 8px', borderRadius: '6px', cursor: 'pointer',
            border: `1px solid ${P.line}`, background: P.bg3, color: P.text,
            fontSize: '0.72rem', marginBottom: '6px' },
  sess: { display: 'flex', alignItems: 'center', gap: '4px', padding: '6px 7px',
          borderRadius: '6px', cursor: 'pointer', marginBottom: '2px', fontSize: '0.72rem' },
  sessTitle: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  del: { border: 0, background: 'transparent', color: P.faint, cursor: 'pointer',
         fontSize: '0.8rem', lineHeight: 1, padding: '0 2px' },
  main: { position: 'relative', flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' },
  barWrap: { borderBottom: `1px solid ${P.line}`, background: P.bg },
  bar: { display: 'flex', alignItems: 'center', gap: '4px', padding: '6px 10px' },
  barMore: { display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap',
             padding: '0 10px 8px' },
  barTitle: { fontSize: '0.76rem', fontWeight: 600, color: P.text, maxWidth: '300px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  barStatus: { fontSize: '0.65rem', color: P.faint, whiteSpace: 'nowrap' },
  ctlBtn: { display: 'flex', alignItems: 'center', gap: '4px', background: 'transparent',
            color: P.dim, border: '1px solid transparent', borderRadius: '7px',
            fontSize: '0.68rem', padding: '3px 8px', cursor: 'pointer' },
  ctl: { background: P.bg, color: P.dim, border: `1px solid ${P.line}`,
         borderRadius: '7px', fontSize: '0.67rem', padding: '3px 7px', maxWidth: '230px',
         outline: 'none' },
  label: { fontSize: '0.64rem', color: P.faint, whiteSpace: 'nowrap' },
  btn: { background: P.bg, color: P.dim, border: `1px solid ${P.line}`,
         borderRadius: '7px', fontSize: '0.67rem', padding: '3px 9px', cursor: 'pointer' },
  status: { marginLeft: 'auto', fontSize: '0.66rem', color: P.faint, whiteSpace: 'nowrap' },
  stream: { flex: 1, minHeight: 0, overflowY: 'auto', padding: '14px 22px 18px' },
  thread: { maxWidth: '780px', margin: '0 auto', width: '100%' },
  empty: { height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center',
           justifyContent: 'center', gap: '8px', color: P.faint, textAlign: 'center' },
  userWrap: { display: 'flex', justifyContent: 'flex-end', margin: '12px 0' },
  userBubble: { maxWidth: '78%', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                background: P.bubble, borderRadius: '18px 18px 4px 18px', padding: '9px 14px',
                lineHeight: 1.65, color: P.text },
  assistant: { padding: '6px 0 14px', lineHeight: 1.72, whiteSpace: 'pre-wrap',
               wordBreak: 'break-word', fontSize: '0.83rem' },
  role: { fontSize: '0.62rem', fontWeight: 650, color: P.accent2, letterSpacing: '0.04em',
          textTransform: 'uppercase', marginBottom: '3px' },

  /* Thinking block — one quiet row above the answer, like the official app */
  think: { margin: '8px 0 2px' },
  thinkHead: { display: 'flex', alignItems: 'center', gap: '7px', padding: '3px 2px',
               cursor: 'pointer', fontSize: '0.73rem', color: P.dim, userSelect: 'none' },
  thinkBody: { marginLeft: '9px', paddingLeft: '12px', borderLeft: `1.5px solid ${P.line}`,
               marginTop: '2px', paddingTop: '2px', paddingBottom: '4px',
               color: P.faint, fontSize: '0.74rem', lineHeight: 1.75,
               whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '340px',
               overflowY: 'auto' },
  code: { fontFamily: P.mono, fontSize: '0.7rem', background: P.code,
          border: `1px solid ${P.line}`, borderRadius: '6px', padding: '8px 10px',
          overflowX: 'auto', whiteSpace: 'pre', margin: '6px 0' },
  card: { border: `1px solid ${P.line}`, background: P.bg2, borderRadius: '7px',
          margin: '5px 0', overflow: 'hidden' },
  cardHead: { display: 'flex', alignItems: 'center', gap: '6px', padding: '5px 9px',
              cursor: 'pointer', fontSize: '0.69rem' },
  cardBody: { padding: '6px 9px 8px', borderTop: `1px solid ${P.line}`,
              fontFamily: P.mono, fontSize: '0.66rem', whiteSpace: 'pre-wrap',
              wordBreak: 'break-all', maxHeight: '260px', overflowY: 'auto', color: P.dim },
  note: { fontSize: '0.67rem', color: P.faint, padding: '3px 0', lineHeight: 1.5 },
  err: { color: P.red, fontSize: '0.72rem', whiteSpace: 'pre-wrap', padding: '6px 0' },
  composer: { borderTop: `1px solid ${P.line}`, padding: '10px 16px 12px', background: P.bg },
  composerBox: { maxWidth: '780px', margin: '0 auto', border: `1px solid ${P.line}`,
                 borderRadius: '18px', background: P.input || P.white,
                 padding: '10px 12px 9px', boxShadow: '0 1px 2px rgba(31,29,27,0.04)' },
  /* One line by default; grows to exactly as many lines as were typed. */
  ta: { width: '100%', height: '26px', minHeight: '26px', maxHeight: '176px',
        resize: 'none', overflowY: 'hidden',
        boxSizing: 'border-box', borderRadius: '6px', padding: '2px 4px',
        border: 0, background: 'transparent', color: P.text,
        fontFamily: 'inherit', fontSize: '0.8rem', lineHeight: 1.55, outline: 'none' },
  foot: { display: 'flex', alignItems: 'center', gap: '2px', marginTop: '6px' },
  hint: { fontSize: '0.64rem', color: P.faint, flex: 1 },
  cwdChip: { fontSize: '0.66rem', color: P.dim, maxWidth: '190px', overflow: 'hidden',
             textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: '3px 7px',
             borderRadius: '7px', background: 'transparent', border: `1px solid ${P.line}` },
  /* Official composer affordances: coral circle + white up-arrow, and a
     borderless paperclip on the left. */
  send: { display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: '30px', height: '30px', flexShrink: 0, borderRadius: '50%',
          background: P.accent, border: 0, cursor: 'pointer', padding: 0,
          transition: 'filter .12s' },
  stop: { display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: '30px', height: '30px', flexShrink: 0, borderRadius: '50%',
          background: P.bg3, color: P.text, border: `1px solid ${P.line}`,
          cursor: 'pointer', padding: 0 },
  iconBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center',
             background: 'transparent', color: P.faint, border: 0,
             borderRadius: '50%', width: '28px', height: '28px', cursor: 'pointer',
             lineHeight: 1, padding: 0 },

  /* Attachments */
  attachBar: { display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' },
  attachChip: { display: 'flex', alignItems: 'center', gap: '5px', maxWidth: '210px',
                padding: '3px 6px', borderRadius: '6px', fontSize: '0.65rem',
                background: P.bg3, border: `1px solid ${P.line}`, color: P.dim },
  thumb: { width: '20px', height: '20px', borderRadius: '4px', objectFit: 'cover' },
  attachNote: { fontSize: '0.62rem', color: P.faint, marginTop: '4px', lineHeight: 1.5 },

  /* In-plugin permission approval card (Claude Code --permission-prompt-tool) */
  apprWrap: { position: 'absolute', right: '16px', bottom: '128px', zIndex: 70,
              width: '382px', maxWidth: 'calc(100% - 32px)', display: 'flex',
              flexDirection: 'column', gap: '8px' },
  apprCard: { background: P.bg2, border: `2px solid ${P.accent}`, borderRadius: '10px',
              boxShadow: '0 8px 28px rgba(0,0,0,0.18)', overflow: 'hidden', outline: 'none' },
  apprHead: { display: 'flex', alignItems: 'center', gap: '7px', padding: '8px 11px',
              background: P.accent, color: P.white, fontSize: '0.72rem', fontWeight: 650 },
  apprCount: { marginLeft: 'auto', fontSize: '0.63rem', fontWeight: 500, opacity: 0.9 },
  apprBody: { padding: '9px 11px' },
  apprTool: { fontFamily: P.mono, fontSize: '0.7rem', color: P.accent2,
              fontWeight: 650, marginBottom: '5px' },
  apprInput: { fontFamily: P.mono, fontSize: '0.66rem', color: P.dim,
               background: P.code, border: `1px solid ${P.line}`, borderRadius: '6px',
               padding: '6px 8px', maxHeight: '116px', overflowY: 'auto',
               whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
  apprMeta: { display: 'flex', alignItems: 'center', gap: '8px', marginTop: '7px',
              fontSize: '0.63rem', color: P.faint },
  apprActions: { display: 'flex', gap: '6px', padding: '8px 11px',
                 borderTop: `1px solid ${P.line}`, flexWrap: 'wrap' },
  apprBtn: { borderRadius: '6px', padding: '5px 11px', fontSize: '0.69rem',
             fontWeight: 600, cursor: 'pointer', border: `1px solid ${P.line}` },
  apprAllow: { background: P.green, color: P.white, border: 0 },
  apprAlways: { background: P.bg3, color: P.text },
  apprDeny: { background: 'transparent', color: P.red },
  apprKeys: { marginLeft: 'auto', alignSelf: 'center', fontSize: '0.61rem', color: P.faint },
  permChip: { display: 'inline-flex', alignItems: 'center', gap: '4px',
              fontSize: '0.65rem', color: P.dim, padding: '3px 7px',
              borderRadius: '5px', background: P.bg3, border: `1px solid ${P.line}`,
              cursor: 'pointer', whiteSpace: 'nowrap' },
  permDot: { width: '6px', height: '6px', borderRadius: '50%', background: P.green },
  permDotOff: { width: '6px', height: '6px', borderRadius: '50%', background: P.faint },

  /* Thinking chain */
  trace: { border: `1px solid ${P.line}`, background: P.bg2, borderRadius: '8px',
           margin: '8px 0 12px', overflow: 'hidden' },
  traceHead: { display: 'flex', alignItems: 'center', gap: '7px', padding: '6px 10px',
               cursor: 'pointer', fontSize: '0.68rem', fontWeight: 600 },
  traceBody: { borderTop: `1px solid ${P.line}`, padding: '6px 10px 9px',
               maxHeight: '270px', overflowY: 'auto' },
  traceRow: { display: 'flex', gap: '8px', padding: '3px 0', fontSize: '0.66rem',
              lineHeight: 1.5, borderBottom: `1px dashed ${P.line}` },
  traceKind: { minWidth: '62px', color: P.faint, fontFamily: P.mono, fontSize: '0.62rem' },
  traceText: { flex: 1, color: P.dim, whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  thinkCard: { borderLeft: `3px solid ${P.accent}`, background: P.bg2 },

  /* Model picker anchored to the bottom-right of the composer. */
  pickWrap: { position: 'relative', display: 'flex', alignItems: 'center' },
  pickBtn: { display: 'flex', alignItems: 'center', gap: '3px', maxWidth: '210px',
             background: 'transparent', border: 0, borderRadius: '8px',
             color: P.dim, fontSize: '0.69rem', padding: '5px 6px', cursor: 'pointer' },
  pickName: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              fontWeight: 600, color: P.text },
  overlay: { position: 'fixed', inset: 0, zIndex: 50, background: 'transparent' },
  pop: { position: 'absolute', right: 0, bottom: '38px', width: '338px', zIndex: 60,
         display: 'flex', flexDirection: 'column', maxHeight: '404px', overflow: 'hidden',
         background: P.white, border: `1px solid rgba(31,29,27,0.09)`, borderRadius: '14px',
         boxShadow: '0 10px 34px rgba(31,29,27,0.14), 0 2px 6px rgba(31,29,27,0.06)' },
  popHead: { padding: '11px 12px 9px', borderBottom: `1px solid ${P.line}` },
  popTitle: { fontSize: '0.7rem', fontWeight: 650, marginBottom: '7px', color: P.text },
  popSearch: { width: '100%', boxSizing: 'border-box', borderRadius: '8px',
               padding: '6px 9px', fontSize: '0.72rem', color: P.text,
               background: P.bg2, border: `1px solid transparent`, outline: 'none' },
  popList: { flex: 1, minHeight: 0, overflowY: 'auto', padding: '5px 6px 8px' },
  grp: { padding: '9px 8px 4px', fontSize: '0.62rem', fontWeight: 650,
         color: P.faint, letterSpacing: '0.02em',
         display: 'flex', alignItems: 'center', gap: '6px' },
  opt: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 9px',
         borderRadius: '8px', cursor: 'pointer', fontSize: '0.73rem' },
  optName: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  optTag: { fontSize: '0.6rem', color: P.faint },
  popFoot: { padding: '7px 12px', borderTop: `1px solid ${P.line}`,
             fontSize: '0.62rem', lineHeight: 1.5, color: P.faint },

  /* Settings page */
  setWrap: { display: 'flex', height: '100%', minHeight: 0, background: P.bg, color: P.text,
             fontSize: '0.75rem' },
  setNav: { width: '186px', minWidth: '186px', borderRight: `1px solid ${P.line}`,
            background: P.bg2, padding: '10px 8px', overflowY: 'auto' },
  setNavBtn: { width: '100%', textAlign: 'left', padding: '7px 9px', marginBottom: '3px',
               borderRadius: '6px', border: 0, background: 'transparent', color: P.dim,
               fontSize: '0.71rem', cursor: 'pointer' },
  setMain: { flex: 1, minWidth: 0, overflowY: 'auto', padding: '14px 18px 30px' },
  setTitle: { fontSize: '0.95rem', fontWeight: 650, marginBottom: '3px' },
  setSub: { fontSize: '0.67rem', color: P.faint, lineHeight: 1.6, marginBottom: '12px' },
  setActions: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap',
                padding: '8px 0 12px', borderBottom: `1px solid ${P.line}`, marginBottom: '10px' },
  field: { padding: '9px 0', borderBottom: `1px solid ${P.line}` },
  fieldLabel: { fontSize: '0.71rem', fontWeight: 600, marginBottom: '4px' },
  fieldMap: { fontSize: '0.61rem', fontFamily: P.mono, color: P.accent2, marginBottom: '3px' },
  fieldHelp: { fontSize: '0.63rem', color: P.faint, marginTop: '3px', lineHeight: 1.5 },
  input: { width: '100%', boxSizing: 'border-box', background: P.bg2, color: P.text,
           border: `1px solid ${P.line}`, borderRadius: '6px', padding: '5px 8px',
           fontSize: '0.7rem', fontFamily: 'inherit', outline: 'none' },
  textarea: { width: '100%', boxSizing: 'border-box', minHeight: '58px', background: P.bg2,
              color: P.text, border: `1px solid ${P.line}`, borderRadius: '6px',
              padding: '6px 8px', fontSize: '0.69rem', fontFamily: P.mono,
              lineHeight: 1.5, resize: 'vertical', outline: 'none' },
  toggle: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' },
  toggleBox: { width: '30px', height: '17px', borderRadius: '9px', position: 'relative',
               transition: 'background .15s', flexShrink: 0 },
  toggleDot: { width: '13px', height: '13px', borderRadius: '50%', background: P.white,
               position: 'absolute', top: '2px', transition: 'left .15s' },
  primary: { background: P.accent, color: P.white, border: 0, borderRadius: '6px',
             padding: '6px 14px', fontSize: '0.71rem', fontWeight: 600, cursor: 'pointer' },
  secondary: { background: P.bg3, color: P.text, border: `1px solid ${P.line}`,
               borderRadius: '6px', padding: '6px 12px', fontSize: '0.71rem', cursor: 'pointer' },
  infoBox: { background: P.bg2, border: `1px solid ${P.line}`, borderRadius: '8px',
             padding: '9px 11px', fontSize: '0.68rem', lineHeight: 1.7, marginBottom: '12px' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.68rem' },
  th: { textAlign: 'left', padding: '6px 8px', borderBottom: `1px solid ${P.line}`,
        color: P.faint, fontWeight: 600, fontSize: '0.64rem' },
  td: { padding: '6px 8px', borderBottom: `1px solid ${P.line}`, verticalAlign: 'top' },
  pill: { display: 'inline-block', padding: '1px 7px', borderRadius: '9px',
          fontSize: '0.6rem', fontWeight: 650 },
  log: { fontFamily: P.mono, fontSize: '0.64rem', background: P.code,
         border: `1px solid ${P.line}`, borderRadius: '6px', padding: '8px 10px',
         maxHeight: '210px', overflowY: 'auto', whiteSpace: 'pre-wrap',
         wordBreak: 'break-all', lineHeight: 1.6 }
})

let S = makeStyles(PALETTES.claude)
let P = PALETTES.claude
const themeTick = atom(0)

function setPalette(name) {
  P = PALETTES[name] || PALETTES.claude
  S = makeStyles(P)
  themeTick.set(themeTick.get() + 1)
}

/** Official Claude starburst — 12 rays of uneven length, solid centre.
    Vector path is the official brand mark on a 24x24 grid, so it stays
    crisp at 13px in the status bar and at 88px on the empty state. */
const CLAUDE_MARK_PATH = 'm4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z'
const CLAUDE_CORAL = '#C47C5E'
function ClaudeMark({ size = 18, color = null }) {
  return h('svg', {
    width: size, height: size, viewBox: '0 0 24 24',
    style: { display: 'block', flexShrink: 0 },
    'aria-label': 'Claude', role: 'img'
  },
    h('path', { d: CLAUDE_MARK_PATH, fill: color || CLAUDE_CORAL }))
}

/** Resize the composer textarea to its content: 1 row empty, N rows typed. */
function growTextarea(el) {
  if (!el) return
  const max = 176
  // Measure from a fixed one-line box: `height:auto` depends on the flex
  // parent and would report the whole container height.
  el.style.height = '26px'
  const need = el.scrollHeight || 26
  el.style.height = Math.max(26, Math.min(need, max)) + 'px'
  el.style.overflowY = need > max ? 'auto' : 'hidden'
}

/** Attachment affordance: the official desktop app uses a thin paperclip. */
function Paperclip({ size = 15, color = null }) {
  return h('svg', {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: color || 'currentColor', strokeWidth: 1.6,
    strokeLinecap: 'round', strokeLinejoin: 'round',
    style: { display: 'block', flexShrink: 0 }, 'aria-label': '附件', role: 'img'
  },
    h('path', { d: 'M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48' }))
}

/** Send affordance: the official desktop app uses a white up-arrow on a
    coral circle, not a text button. */
function ArrowUp({ size = 15, color = '#FFFFFF' }) {
  return h('svg', {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: color, strokeWidth: 2.4, strokeLinecap: 'round', strokeLinejoin: 'round',
    style: { display: 'block' }, 'aria-label': '发送', role: 'img'
  }, h('path', { d: 'M12 19V5M5 12l7-7 7 7' }))
}

/** Thin chevron used by every foldable row (thinking, tools, model list). */
function Chevron({ open, size = 11, color = null }) {
  return h('svg', {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: color || 'currentColor', strokeWidth: 2.2,
    strokeLinecap: 'round', strokeLinejoin: 'round',
    style: { display: 'block', flexShrink: 0,
             transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }
  }, h('path', { d: 'M9 5l7 7-7 7' }))
}

/* ------------------------------------------------------------------ */
/* Backend transport                                                    */
/* ------------------------------------------------------------------ */
/* The app's own door is `ctx.rest` (authenticated `/api/plugins/<id>`).
   When the gateway has a dashboard auth provider configured, a window
   without a session cookie gets 401 / 404 on that door — the panel then
   says "backend not connected" even though the routes are mounted. This
   plugin therefore serves its SAME router on a loopback port
   (`/relay` in plugin_api.py); we fall back to it, so the panel works in
   every auth mode. Paths stay identical: `/health`, `/chat`, ... */
/* The relay token is generated per installation by the backend — deliberately
   NOT a constant in this file: a value published in a public repository would
   be known to everyone and protect nothing. It is fetched once over loopback
   (`/relay/handshake`, which refuses http(s) origins) and cached here; a
   gateway restart rotates it and the 403 path below re-handshakes. */
let relayToken = ''
const RELAY_PORTS = [47823, 47824, 47825, 47826, 47827, 47828]
let relayBase = null
const channel = atom('网关')

async function relayHandshake(base) {
  const res = await fetch(base + '/relay/handshake')
  if (!res.ok) throw new Error('handshake HTTP ' + res.status)
  const data = await res.json()
  relayToken = String((data && data.token) || '')
  if (!relayToken) throw new Error('handshake returned no token')
  return relayToken
}

async function relayCall(path, opts) {
  const bases = relayBase ? [relayBase] : RELAY_PORTS.map((port) => 'http://127.0.0.1:' + port)
  let last = null
  for (const base of bases) {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        if (!relayToken) await relayHandshake(base)
        const res = await fetch(base + path, {
          method: (opts && opts.method) || 'GET',
          headers: { 'content-type': 'application/json', 'x-ccp-token': relayToken },
          body: opts && opts.body != null ? JSON.stringify(opts.body) : undefined
        })
        if (res.status === 403 && attempt === 0) { relayToken = ''; continue }
        if (!res.ok) {
          const text = await res.text()
          throw new Error('HTTP ' + res.status + ' ' + text.slice(0, 200))
        }
        relayBase = base
        return await res.json()
      } catch (err) {
        last = err
        if (attempt === 0) { relayToken = ''; continue }
        break
      }
    }
  }
  throw last || new Error('本机直连端口不可达')
}

/** Single entry for every backend call: gateway door first, loopback relay
 *  when the gateway refuses the window's credentials. */
/* Display text the API produces (settings schema, capability matrix, upgrade log,
   diagnostics) is translated server-side, so every call carries the UI language. */
function withLang(path) {
  const p = String(path || '')
  const lang = readLang()
  if (!lang) return p
  return p + (p.includes('?') ? '&' : '?') + 'lang=' + encodeURIComponent(lang)
}

async function api(path, opts) {
  if (!ctxRef) throw new Error('插件上下文未就绪')
  const target = withLang(path)
  if (relayBase && channel.get() === '直连') return relayCall(target, opts)
  try {
    const out = await ctxRef.rest(target, opts)
    if (!relayBase) channel.set('网关')
    return out
  } catch (err) {
    const text = String((err && err.message) || err)
    if (!/\b(401|403|404)\b/.test(text)) throw err
    const out = await relayCall(target, opts)
    channel.set('直连')
    return out
  }
}

/* ------------------------------------------------------------------ */
/* Shared state                                                         */
/* ------------------------------------------------------------------ */
const sessions = atom([{
  id: 'cc-1', title: '新建会话', model: null, cwd: '', resumeId: null,
  messages: [], traces: [], attachments: [], createdAt: Date.now()
}])
const activeId = atom('cc-1')
const draft = atom('')
const busy = atom(false)
const status = atom('正在连接 Hermes…')
const backend = atom({ ok: false, groups: [], models: [], recommended: null,
                       version: '', total: 0, defaultCwd: '', error: '', raw: '',
                       claudeOk: true, claudeProblem: '' })
const view = atom('normal')
const effort = atom('')
const toolPolicy = atom('auto')
const modelPicker = atom(false)
const modelQuery = atom('')
const settingsSchema = atom([])
const settingsValues = atom({})
const settingsSaved = atom({})
const cliInfo = atom({ flags: [], features: [], slash_commands: [], subcommands: [],
                       mapped_flags: [], mapped_settings_keys: [], version: '' })
const settingsTab = atom('模型与推理')
const settingsDirty = atom(false)
const upgrade = atom({ running: false, checked: false, current: '', latest: '',
                       available: false, log: [], exit: null, before: '', after: '',
                       error: '', method: '', installDir: '' })
const settingsLoaded = atom(false)
const approvals = atom([])

/* CLI transcripts live in ~/.claude/projects/*.jsonl. The plugin lists them
   next to its own sessions so the sidebar is one history, like the desktop
   app, and can rename / archive / delete them. */
const history = atom({ items: [], projects: [], loading: false, loaded: false, q: '',
                       error: '', total: 0, archived: 0, trash: 0 })
const histMenu = atom(null)      /* { id, x, y, item } */
const histRenaming = atom(null)  /* session id being renamed inline */
const histConfirm = atom(null)   /* session id awaiting a second click */
const histTab = atom('active')   /* active | archived | trash */
const mobileOpen = atom(false)
const mobileState = atom({ loading: false, ok: false, urls: [], qr: '', hint: '', error: '' })

const PERMISSION_MODES = ['acceptEdits', 'auto', 'manual', 'plan', 'dontAsk', 'bypassPermissions']
const PERMISSION_LABELS = {
  acceptEdits: '接受编辑', auto: '自动', manual: '手动',
  plan: '计划', dontAsk: '不询问', bypassPermissions: '绕过权限'
}

let ctxRef = null
let pollTimer = null
let pollJob = null
let pollCursor = 0
let pollSid = null
let pollActive = false
let sawDelta = false
let msgSeq = 0
let traceSeq = 0
let booted = false
let persistTimer = null
let upgradeTimer = null
let fileInputRef = null

/* ------------------------------------------------------------------ */
/* State helpers                                                        */
/* ------------------------------------------------------------------ */
const getSession = (id) => sessions.get().find((s) => s.id === id) || null
const cfg = () => settingsValues.get() || {}

function schedulePersist() {
  if (!cfg().session_persist || !ctxRef || !ctxRef.storage) return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    try {
      const slim = sessions.get().map((s) => ({
        id: s.id, title: s.title, model: s.model, cwd: s.cwd,
        resumeId: s.resumeId, createdAt: s.createdAt, fromHistory: s.fromHistory,
        /* A reopened CLI transcript can be thousands of rows; it is re-read
           from disk on boot instead of being copied into plugin storage. */
        messages: s.fromHistory ? [] : (s.messages || []).slice(-120),
        traces: (s.traces || []).slice(-20)
      }))
      ctxRef.storage.set('sessions', slim)
      ctxRef.storage.set('activeId', activeId.get())
    } catch (_) { /* storage may be unavailable on older hosts */ }
  }, 400)
}

function patch(id, fn) {
  sessions.set(sessions.get().map((s) => (s.id === id ? fn(s) : s)))
  schedulePersist()
}

function append(id, msg) {
  patch(id, (s) => ({ ...s, messages: [...(s.messages || []).slice(-299),
    { key: ++msgSeq, turn: s.turn || 0, ...msg }] }))
}

/** The CLI streams reasoning in many small deltas. Appending one bubble per
 *  delta shattered a single chain into a dozen rows, so every chunk of the
 *  same turn is merged into the block that is still streaming. */
function appendThinking(id, text) {
  const chunk = String(text || '')
  if (!chunk) return
  const s = getSession(id)
  if (!s) return
  const last = (s.messages || [])[s.messages.length - 1]
  if (last && last.role === 'thinking' && last.streaming) {
    patch(id, (x) => ({ ...x, messages: [...x.messages.slice(0, -1),
      { ...last, text: (last.text || '') + chunk }] }))
    return
  }
  finishStream(id)
  append(id, { role: 'thinking', text: chunk, streaming: true })
}

/** Close every thinking block of the running turn (end of reply / error). */
function sealThinking(id) {
  patch(id, (s) => {
    const turn = s.turn || 0
    let changed = false
    const messages = (s.messages || []).map((m) => {
      if (m.role === 'thinking' && m.streaming &&
          (m.turn == null || (m.turn || 0) === turn)) {
        changed = true
        return { ...m, streaming: false }
      }
      return m
    })
    return changed ? { ...s, messages } : s
  })
}

/** Everything the current turn has already put on screen as "thinking". */
function turnThinking(id) {
  const s = getSession(id)
  if (!s) return ''
  const turn = s.turn || 0
  return (s.messages || [])
    .filter((m) => m.role === 'thinking' && (m.turn || 0) === turn)
    .map((m) => m.text || '').join('\n')
}

function patchLastAssistant(id, text) {
  const s = getSession(id)
  if (!s) return
  const last = (s.messages || [])[s.messages.length - 1]
  if (last && last.role === 'assistant' && last.streaming) {
    patch(id, (x) => ({
      ...x,
      messages: [...x.messages.slice(0, -1), { ...last, text: (last.text || '') + text }]
    }))
  } else {
    if (last && last.streaming) finishStream(id)
    append(id, { role: 'assistant', text, streaming: true })
  }
}

function finishStream(id) {
  const s = getSession(id)
  if (!s || !(s.messages || []).length) return
  const last = s.messages[s.messages.length - 1]
  if (last && last.streaming) {
    patch(id, (x) => ({
      ...x,
      messages: [...x.messages.slice(0, -1), { ...last, streaming: false }]
    }))
  }
}

function shortTool(name, input) {
  let hint = ''
  try {
    const v = input && (input.command || input.file_path || input.pattern ||
                        input.path || input.query || input.description)
    if (v) hint = ' · ' + String(v).slice(0, 100)
  } catch (_) { /* ignore */ }
  return (name || 'tool') + hint
}

function hasAssistantText(id) {
  const s = getSession(id)
  return !!(s && (s.messages || []).some((m) => m.role === 'assistant' && (m.text || '').trim()))
}

/** Append to the current run's thinking/tool chain (the visible "chain"). */
function tracePush(id, item) {
  patch(id, (s) => {
    const traces = (s.traces || []).slice()
    const turn = s.turn || 0
    if (!traces.length || traces[traces.length - 1].closed ||
        (traces[traces.length - 1].turn || 0) !== turn) {
      traces.push({ key: ++traceSeq, turn, items: [], started: Date.now(), closed: false })
    }
    const cur = traces[traces.length - 1]
    const items = cur.items.slice()
    const last = items[items.length - 1]
    if (item.kind === 'reasoning' && last && last.kind === 'reasoning') {
      items[items.length - 1] = { ...last, text: (last.text || '') + (item.text || ''),
                                  chars: (last.chars || 0) + (item.chars || 0) }
    } else {
      items.push({ ...item, ts: Date.now() })
    }
    traces[traces.length - 1] = { ...cur, items, ended: Date.now() }
    return { ...s, traces }
  })
}

function closeTrace(id, error) {
  patch(id, (s) => {
    const traces = (s.traces || []).slice()
    if (!traces.length) return s
    traces[traces.length - 1] = { ...traces[traces.length - 1], closed: true,
                                  ended: Date.now(), error: error || null }
    return { ...s, traces }
  })
}

function applyEvent(id, ev) {
  const v = view.get()
  const c = cfg()
  const showThinking = c.show_thinking !== false
  const showTools = c.show_tool_cards !== false
  const showResults = c.show_tool_results !== false
  const compact = v === 'compact'

  if (ev.kind === 'init') {
    status.set('运行中 · ' + (ev.model || ''))
    if (ev.session_id) patch(id, (s) => ({ ...s, resumeId: ev.session_id }))
    return
  }
  if (ev.kind === 'delta') {
    sawDelta = true
    patchLastAssistant(id, ev.text || '')
    return
  }
  if (ev.kind === 'reasoning_delta' || ev.kind === 'thinking_delta') {
    const text = ev.text || ''
    if (showThinking) appendThinking(id, text)
    tracePush(id, { kind: 'reasoning', text, chars: text.length })
    return
  }
  if (ev.kind === 'reasoning_done') {
    tracePush(id, { kind: 'note', text: `思考结束 · ${ev.chars || 0} 字 · 上游工具调用 ${ev.tools || 0} 次` })
    return
  }
  if (ev.kind === 'tool_call') {
    tracePush(id, { kind: 'tool', name: ev.name, text: (ev.args || '').slice(0, 300) })
    return
  }
  if (ev.kind === 'usage') {
    tracePush(id, { kind: 'usage', text: `in ${ev.input_tokens || 0} / out ${ev.output_tokens || 0} tokens` })
    return
  }
  if (ev.kind === 'blocks') {
    for (const b of ev.blocks || []) {
      if (b.type === 'text') {
        if (sawDelta) finishStream(id)
        else append(id, { role: 'assistant', text: b.text || '' })
      } else if (b.type === 'thinking' && showThinking && !compact) {
        const text = String(b.text || '')
        // The CLI re-sends the whole thinking block after the deltas; only
        // merge what has not been seen yet instead of duplicating the chain.
        if (text && !turnThinking(id).includes(text.trim())) {
          appendThinking(id, text)
          tracePush(id, { kind: 'reasoning', text, chars: text.length })
        }
      } else if (b.type === 'tool' && showTools && !compact) {
        append(id, { role: 'tool', name: b.name, hint: shortTool(b.name, b.input),
                     input: b.input, id: b.id, state: 'running' })
        tracePush(id, { kind: 'tool', name: b.name,
                        text: shortTool(b.name, b.input) })
      } else if (b.type === 'tool_result' && showResults && !compact) {
        append(id, { role: 'tool', name: 'result', hint: '工具返回 · ' + (b.id || ''),
                     text: String(b.text || '').slice(0, 1600), state: 'done' })
        tracePush(id, { kind: 'result', name: b.id || 'tool',
                        text: String(b.text || '').slice(0, 400) })
      }
    }
    return
  }
  if (ev.kind === 'result') {
    if (!ev.ok) {
      append(id, { role: 'error', text: 'Claude Code: ' + (ev.error || ev.text || '请求失败') })
    } else if (!sawDelta && ev.text && !hasAssistantText(id)) {
      append(id, { role: 'assistant', text: ev.text })
    }
    finishStream(id)
    return
  }
  if (ev.kind === 'permission_request') {
    const list = approvals.get()
    if (!list.some((a) => a.id === ev.id)) {
      approvals.set([...list, {
        id: ev.id, job_id: ev.job_id, tool_name: ev.tool_name,
        input: ev.input || {}, tool_use_id: ev.tool_use_id,
        deadline: ev.deadline, timeout: ev.timeout || 120, at: Date.now()
      }])
    }
    status.set('等待审批 · ' + (ev.tool_name || '工具调用'))
    tracePush(id, { kind: 'note', text: `权限审批请求 → ${ev.tool_name || ''}` })
    return
  }
  if (ev.kind === 'permission_resolved') {
    approvals.set(approvals.get().filter((a) => a.id !== ev.id))
    const label = ev.action === 'timeout' ? '审批超时自动拒绝'
      : ev.action === 'deny' ? '已拒绝'
      : ev.action === 'always_allow' ? '始终允许' : '已允许'
    tracePush(id, { kind: 'note', text: `权限审批 ${label} · ${ev.tool_name || ''}` })
    status.set('运行中 · ' + label)
    return
  }
  if (ev.kind === 'log') {
    if (v === 'verbose') append(id, { role: 'log', text: ev.text || '' })
    else tracePush(id, { kind: 'log', text: String(ev.text || '').slice(0, 200) })
    return
  }
  if (ev.kind === 'done') {
    finishStream(id)
    sealThinking(id)
    busy.set(false)
    status.set(ev.error ? '错误' : '就绪')
    closeTrace(id, ev.error)
    stopPolling()
  }
}

/* ------------------------------------------------------------------ */
/* Backend I/O                                                          */
/* ------------------------------------------------------------------ */
function stopPolling() {
  pollActive = false
  if (pollTimer) {
    try { pollTimer() } catch (_) { /* ignore */ }
    pollTimer = null
  }
}

async function pollOnce() {
  if (!pollActive || !pollJob || !ctxRef) return
  const sid = pollSid
  try {
    const r = await api('/poll?job_id=' + encodeURIComponent(pollJob) + '&cursor=' + pollCursor)
    pollCursor = r.cursor
    for (const ev of r.events || []) applyEvent(sid, ev)
    if (r.session_id) patch(sid, (s) => ({ ...s, resumeId: r.session_id }))
    if (r.done) {
      finishStream(sid)
      sealThinking(sid)
      busy.set(false)
      status.set(r.error ? '错误 · ' + String(r.error).slice(0, 60) : '就绪')
      if (r.error) {
        append(sid, { role: 'error', text: String(r.error) + (r.stderr ? '\n' + r.stderr : '') })
      }
      closeTrace(sid, r.error)
      stopPolling()
    }
  } catch (err) {
    busy.set(false)
    status.set('轮询失败 · ' + String((err && err.message) || err).slice(0, 60))
    closeTrace(sid, String(err))
    stopPolling()
  }
}

function startPolling() {
  stopPolling()
  pollActive = true
  if (ctxRef) pollTimer = ctxRef.setInterval(() => void pollOnce(), 350)
}

function applyUiFromSettings(values) {
  if (!values || typeof values !== 'object') return
  if (values.effort !== undefined) effort.set(values.effort)
  if (values.tool_policy !== undefined) toolPolicy.set(values.tool_policy)
  if (values.view_mode !== undefined) view.set(values.view_mode)
  setPalette(values.brand_theme || 'claude')
}

/* ---- in-plugin permission approvals --------------------------------- */
const permMode = () => String(cfg().permission_mode || 'acceptEdits')
const approvalOn = () => String(cfg().permission_prompts || 'host') === 'host'

async function persistSetting(key, value) {
  updateSetting(key, value)
  if (!ctxRef) return
  try {
    const r = await api('/settings', {
      method: 'POST', body: { values: { ...cfg(), [key]: value } }
    })
    settingsValues.set(r.values || {})
    settingsSaved.set(r.values || {})
    settingsDirty.set(false)
  } catch (err) {
    status.set('设置保存失败 · ' + String((err && err.message) || err).slice(0, 50))
  }
}

function cyclePermissionMode() {
  const cur = permMode()
  const i = PERMISSION_MODES.indexOf(cur)
  const next = PERMISSION_MODES[(i + 1 + PERMISSION_MODES.length) % PERMISSION_MODES.length]
  void persistSetting('permission_mode', next)
  status.set(`权限模式 → ${next}（${PERMISSION_LABELS[next]}）· Shift+Tab 继续切换`)
}

function toggleApprovalMode() {
  const next = approvalOn() ? 'none' : 'host'
  void persistSetting('permission_prompts', next)
  status.set(next === 'host'
    ? '审批已开启 · 工具调用会在插件内弹窗询问'
    : '审批已关闭 · 需要授权的工具将被直接拒绝')
}

function decideFirst(action) {
  const list = approvals.get()
  if (!list.length) {
    status.set('当前没有待审批的操作')
    return
  }
  void decideApproval(list[0].id, action)
}

async function decideApproval(id, action) {
  if (!ctxRef || !id) return
  approvals.set(approvals.get().filter((a) => a.id !== id))
  try {
    await api('/approvals/decide', { method: 'POST', body: { id, action } })
    status.set(action === 'deny' ? '已拒绝该工具调用' : '已批准该工具调用')
  } catch (err) {
    status.set('审批提交失败 · ' + String((err && err.message) || err).slice(0, 60))
    void refreshApprovals()
  }
}

async function refreshApprovals() {
  if (!ctxRef) return
  try {
    const r = await api('/approvals')
    const current = approvals.get()
    const seen = new Set(current.map((a) => a.id))
    approvals.set([...current, ...(r.pending || []).filter((a) => !seen.has(a.id))])
  } catch (_) { /* backend may still be mounting */ }
}

function backendErrorText(err) {
  const raw = String((err && err.message) || err || '')
  if (/\b404\b/.test(raw)) {
    return '后端未挂载（404）：当前工作区 profile 没有启用该插件的 Python 后端。请在 `profiles/<工作区>/config.yaml` 的 `plugins.enabled` 中加入 claude-code-parity，然后重试。'
  }
  if (/\b401\b|\b403\b/.test(raw)) return '没有权限访问插件后端（401/403）：请重新登录 Hermes Desktop 或检查会话凭据。'
  if (/Failed to fetch|NetworkError|ECONN|10061|fetch failed/i.test(raw)) {
    return '连不上 Hermes 后端：请确认 Hermes Desktop / Gateway 正在运行，然后重试。'
  }
  return raw.slice(0, 200)
}

async function loadBackend(probe, retry = 2) {
  if (!ctxRef) return
  try {
    const [health, m, set] = await Promise.all([
      api('/health'),
      api('/models?probe=' + (probe ? 'true' : 'false')),
      api('/settings')
    ])
    backend.set({
      ok: true, groups: m.groups || [], models: m.models || [],
      recommended: m.recommended, version: health.claude_version || set.claude_version || '',
      total: m.total || 0, defaultCwd: m.default_cwd || '', error: '',
      claudeOk: health.claude_ok !== false, claudeProblem: health.claude_problem || ''
    })
    settingsSchema.set(set.schema || [])
    settingsValues.set(set.values || {})
    settingsSaved.set(set.values || {})
    cliInfo.set(set.cli || {})
    upgrade.set({ ...upgrade.get(), current: set.claude_version || '',
                  installDir: health.install_dir || set.install_dir || '' })
    settingsLoaded.set(true)
    settingsDirty.set(false)
    applyUiFromSettings(set.values || {})
    const rec = m.recommended
    sessions.set(sessions.get().map((s) => ({
      ...s,
      model: s.model || rec,
      cwd: s.cwd || m.default_cwd || ''
    })))
    status.set(health.claude_ok === false
      ? 'Claude Code 安装损坏 · 可在「设置 → 升级与诊断」修复'
      : '就绪')
  } catch (err) {
    if (retry > 0) {
      status.set('正在连接插件后端…（重试 ' + (3 - retry) + '/3）')
      setTimeout(() => void loadBackend(probe, retry - 1), 900)
      return
    }
    const msg = backendErrorText(err)
    backend.set({ ...backend.get(), error: msg,
                  raw: String((err && err.message) || err || '').slice(0, 300) })
    status.set('后端不可达 · 点击重试')
  }
}

async function sendMessage() {
  const text = draft.get().trim()
  const s = getSession(activeId.get())
  if ((!text && !(s && (s.attachments || []).length)) || !s || busy.get() || !ctxRef) return
  const pick = s.model || backend.get().recommended
  const row = (backend.get().models || []).find((m) => m.id === pick)
  if (!row) {
    status.set('请在输入框右下角选择一个模型')
    return
  }
  const attachments = (s.attachments || []).slice()
  // Every send opens a new turn: thinking blocks from earlier rounds can then
  // never be mixed into — or appended after — the fresh answer.
  patch(s.id, (x) => ({ ...x, turn: (x.turn || 0) + 1 }))
  append(s.id, { role: 'user', text: text || '（附件）',
                 attachments: attachments.map((a) => ({ name: a.name, kind: a.kind, url: a.url })) })
  if (s.title === '新建会话') {
    patch(s.id, (x) => ({ ...x, title: (text || attachments[0]?.name || '新建会话')
      .replace(/\s+/g, ' ').slice(0, 28) }))
  }
  patch(s.id, (x) => ({ ...x, attachments: [], fork: false }))
  draft.set('')
  busy.set(true)
  sawDelta = false
  status.set('启动 Claude Code…')
  try {
    const r = await api('/chat', {
      method: 'POST',
      body: {
        text,
        provider: row.provider,
        model: row.model,
        effort: effort.get(),
        tool_policy: toolPolicy.get(),
        view_mode: view.get(),
        session_key: s.id,
        resume_id: s.resumeId || undefined,
        fork_session: s.fork ? true : undefined,
        cwd: s.cwd || undefined,
        attachments: attachments.map((a) => ({
          path: a.path, name: a.name, mime: a.mime, kind: a.kind
        }))
      }
    })
    pollJob = r.job_id
    pollCursor = 0
    pollSid = s.id
    status.set('运行中 · ' + (r.model || ''))
    startPolling()
  } catch (err) {
    busy.set(false)
    status.set('发送失败')
    append(s.id, { role: 'error', text: '发送失败: ' + String((err && err.message) || err) })
  }
}

async function stopRun() {
  if (pollJob && ctxRef) {
    try {
      await api('/cancel', { method: 'POST', body: { job_id: pollJob } })
    } catch (_) { /* ignore */ }
  }
  busy.set(false)
  status.set('已停止')
  closeTrace(activeId.get(), 'cancelled')
  stopPolling()
}

function newSession() {
  const id = 'cc-' + Date.now().toString(36)
  sessions.set([...sessions.get(), {
    id, title: '新建会话', model: backend.get().recommended,
    cwd: backend.get().defaultCwd || '', resumeId: null,
    messages: [], traces: [], attachments: [], createdAt: Date.now()
  }])
  activeId.set(id)
  draft.set('')
  schedulePersist()
  if (typeof host.navigate === 'function') host.navigate('/claude-code')
}

function deleteSession(id) {
  const left = sessions.get().filter((s) => s.id !== id)
  if (!left.length) return
  sessions.set(left)
  if (activeId.get() === id) activeId.set(left[left.length - 1].id)
  schedulePersist()
}

function clearSession(id) {
  patch(id, (s) => ({ ...s, messages: [], traces: [], resumeId: null,
                      title: '新建会话', attachments: [] }))
  status.set('会话已清空')
}

/* ---- CLI session history -------------------------------------------- */
/* The CLI keeps every conversation in ~/.claude/projects/<project>/<id>.jsonl.
   These helpers turn that folder into a browsable sidebar. */

function relTime(ms) {
  if (!ms) return ''
  const diff = Date.now() - ms
  if (diff < 60e3) return '刚刚'
  if (diff < 3600e3) return Math.round(diff / 60e3) + ' 分钟前'
  if (diff < 86400e3) return Math.round(diff / 3600e3) + ' 小时前'
  if (diff < 30 * 86400e3) return Math.round(diff / 86400e3) + ' 天前'
  const d = new Date(ms)
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
    '-' + String(d.getDate()).padStart(2, '0')
}

async function loadHistory(force) {
  const cur = history.get()
  if (cur.loading) return
  if (cur.loaded && !force) return
  const tab = histTab.get()
  history.set({ ...cur, loading: true, error: '' })
  try {
    if (tab === 'trash') {
      const r = await api('/history/trash')
      history.set({ items: [], loading: false, loaded: true, q: history.get().q,
        error: '', total: history.get().total, archived: history.get().archived,
        trash: (r.items || []).length, trashItems: r.items || [],
        projects: history.get().projects || [] })
      return
    }
    const r = await api('/history?limit=400&archived=' + (tab === 'archived' ? 'true' : 'false'))
    history.set({ items: r.items || [], loading: false, loaded: true, q: history.get().q,
      error: '', total: r.total || 0, archived: r.archived || 0,
      trash: r.trash || 0, trashItems: history.get().trashItems || [],
      projects: r.projects || [] })
  } catch (err) {
    history.set({ ...history.get(), loading: false, loaded: true,
      error: String((err && err.message) || err).slice(0, 200) })
  }
}

function setHistTab(tab) {
  histTab.set(tab)
  histMenu.set(null)
  histRenaming.set(null)
  void loadHistory(true)
}

/** Reopen a transcript. Its id is passed to the CLI as --resume, so the next
 *  message continues that very conversation instead of starting a new one. */
async function openHistorySession(item) {
  histMenu.set(null)
  const existing = sessions.get().find((s) => s.resumeId === item.id)
  if (existing) { activeId.set(existing.id); return }
  status.set('正在读取历史会话…')
  try {
    const r = await api('/history/session?id=' + encodeURIComponent(item.id))
    const meta = r.session || item
    const msgs = (r.messages || []).map((m, i) => ({ ...m, key: m.key || i + 1 }))
    const id = 'h-' + item.id
    sessions.set([...sessions.get(), {
      id, title: meta.title || item.title || '历史会话',
      model: backend.get().recommended || null,
      cwd: meta.cwd || item.cwd || backend.get().defaultCwd || '',
      resumeId: item.id, messages: msgs, traces: [], attachments: [],
      createdAt: meta.created || item.created || Date.now(), fromHistory: true
    }])
    msgSeq = Math.max(msgSeq, msgs.length + 1)
    activeId.set(id)
    status.set('已载入历史会话 · 继续发送会接着原会话')
    schedulePersist()
    if (item.unread) void patchFlags(item, { unread: false }, '')
  } catch (err) {
    status.set('历史会话读取失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

/** Re-read a reopened transcript (after a panel reload). */
async function refillHistorySession(row) {
  if (!row || !row.resumeId) return
  try {
    const r = await api('/history/session?id=' + encodeURIComponent(row.resumeId))
    const msgs = (r.messages || []).map((m, i) => ({ ...m, key: m.key || i + 1 }))
    msgSeq = Math.max(msgSeq, msgs.length + 1)
    patch(row.id, (x) => ({ ...x, messages: msgs }))
  } catch (_) { /* archived or removed meanwhile — keep the row as is */ }
}

async function renameHistory(id, title) {
  histRenaming.set(null)
  const clean = String(title || '').trim()
  try {
    await api('/history/rename', { method: 'POST', body: { id, title: clean } })
    history.set({ ...history.get(), items: history.get().items.map((it) =>
      it.id === id ? { ...it, title: clean || it.auto_title || it.title, renamed: !!clean } : it) })
    const local = sessions.get().find((s) => s.resumeId === id)
    if (local && clean) patch(local.id, (x) => ({ ...x, title: clean }))
    status.set(clean ? '已重命名' : '已恢复自动标题')
  } catch (err) {
    status.set('重命名失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

async function archiveHistory(item, archived) {
  histMenu.set(null)
  try {
    await api('/history/archive', { method: 'POST', body: { id: item.id, archived } })
    const local = sessions.get().find((s) => s.resumeId === item.id)
    if (archived && local) deleteSession(local.id)
    status.set(archived ? '已归档 · 可在「已归档」里恢复' : '已取消归档')
    void loadHistory(true)
  } catch (err) {
    status.set('归档失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

async function deleteHistory(item) {
  histMenu.set(null)
  histConfirm.set(null)
  try {
    await api('/history/delete', { method: 'POST', body: { id: item.id } })
    const local = sessions.get().find((s) => s.resumeId === item.id)
    if (local) deleteSession(local.id)
    status.set('已移入回收站 · 可在「回收站」恢复或彻底删除')
    void loadHistory(true)
  } catch (err) {
    status.set('删除失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

async function restoreHistory(item) {
  try {
    await api('/history/restore', { method: 'POST', body: { id: item.id } })
    status.set('已从回收站恢复')
    void loadHistory(true)
  } catch (err) {
    status.set('恢复失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

async function purgeHistory(id) {
  try {
    const r = await api('/history/purge', { method: 'POST', body: id ? { id } : {} })
    status.set('已彻底删除 ' + (r.removed || 0) + ' 个会话')
    histConfirm.set(null)
    void loadHistory(true)
  } catch (err) {
    status.set('彻底删除失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

/* ---- history row actions (official menu parity) --------------------- */
function legacyCopy(text) {
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    return true
  } catch (_) { return false }
}

function copyText(text, okMsg) {
  const done = () => { if (okMsg) status.set(okMsg) }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done)
        .catch(() => { if (legacyCopy(text)) done() })
      return
    }
  } catch (_) { /* fall through */ }
  if (legacyCopy(text)) done()
}

async function patchFlags(item, flags, msg) {
  histMenu.set(null)
  try {
    const r = await api('/history/flags', { method: 'POST',
      body: { id: item.id, ...flags } })
    const items = history.get().items.map((it) => it.id === item.id
      ? { ...it, pinned: !!r.pinned, unread: !!r.unread } : it)
    items.sort((a, b) => ((b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)) ||
      ((b.updated || 0) - (a.updated || 0)))
    history.set({ ...history.get(), items })
    if (msg) status.set(msg)
  } catch (err) {
    status.set('操作失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

function copyHistoryId(item) {
  histMenu.set(null)
  copyText(item.id, '已复制会话 ID · 终端可用 claude --resume ' + item.id.slice(0, 8) + '…')
}

/** Fork: keep the transcript, derive a brand-new session id on the next send. */
function forkHistory(item) {
  histMenu.set(null)
  const id = 'cc-' + Date.now().toString(36)
  sessions.set([...sessions.get(), {
    id, title: '分支 · ' + String(item.title || '').slice(0, 24),
    model: backend.get().recommended || null,
    cwd: item.cwd || backend.get().defaultCwd || '',
    resumeId: item.id, fork: true, fromHistory: false,
    messages: [], traces: [], attachments: [], createdAt: Date.now()
  }])
  activeId.set(id)
  status.set('已创建分支 · 下一句话会从原会话分叉（--fork-session）')
  schedulePersist()
}

async function moveHistory(item, project, label) {
  histMenu.set(null)
  try {
    const r = await api('/history/move', { method: 'POST',
      body: { id: item.id, project } })
    if (r.cwd) {
      const local = sessions.get().find((s) => s.resumeId === item.id)
      if (local) patch(local.id, (x) => ({ ...x, cwd: r.cwd }))
    }
    status.set('已移动到 ' + (label || project))
    void loadHistory(true)
  } catch (err) {
    status.set('移动失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

async function openInTerminal(item) {
  histMenu.set(null)
  try {
    const r = await api('/history/terminal', { method: 'POST', body: { id: item.id } })
    status.set('已在新控制台运行 claude --resume（' + String(r.cwd || '').slice(0, 40) + '）')
  } catch (err) {
    status.set('打开终端失败：' + String((err && err.message) || err).slice(0, 90))
  }
}

async function exportHistory(item) {
  histMenu.set(null)
  try {
    const r = await api('/history/export', { method: 'POST', body: { id: item.id } })
    status.set('已导出 Markdown · ' + String(r.path || '').split(/[\\/]/).pop())
    copyText(String(r.path || ''), '已导出并复制路径 · ' + String(r.path || '').split(/[\\/]/).pop())
  } catch (err) {
    status.set('导出失败：' + String((err && err.message) || err).slice(0, 80))
  }
}

function openInNewTab(item) {
  histMenu.set(null)
  try {
    const w = window.open('/claude-code', '_blank')
    if (w) { status.set('已在新标签页打开 Claude Code'); return }
  } catch (_) { /* host may block popups */ }
  void openHistorySession(item)
}

/** Where the phone can reach this workspace (LAN address + token). */
async function showMobile() {
  mobileOpen.set(true)
  mobileState.set({ ...mobileState.get(), loading: true, error: '' })
  try {
    const r = await api('/mobile')
    mobileState.set({ loading: false, ok: !!r.ok, urls: r.urls || [], qr: r.qr || '',
                      hint: r.hint || '', error: '' })
  } catch (err) {
    mobileState.set({ loading: false, ok: false, urls: [], qr: '', hint: '',
                      error: String((err && err.message) || err).slice(0, 170) })
  }
}

function openClaudeHelp() {
  histMenu.set(null)
  try {
    window.open('https://docs.claude.com/en/docs/claude-code/overview', '_blank')
    status.set('已打开 Claude Code 官方文档')
  } catch (_) {
    status.set('文档地址：docs.claude.com/en/docs/claude-code/overview')
  }
}


/* ---- attachments ---------------------------------------------------- */
async function addFiles(fileList, sid) {
  if (!ctxRef || !fileList || !fileList.length) return
  status.set('正在上传附件…')
  for (const file of Array.from(fileList)) {
    try {
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ''))
        reader.onerror = () => reject(new Error('read failed'))
        reader.readAsDataURL(file)
      })
      const r = await api('/upload', {
        method: 'POST',
        body: { name: file.name, mime: file.type || 'application/octet-stream',
                size: file.size, data: dataUrl, session_key: sid }
      })
      const a = r.attachment
      patch(sid, (s) => ({ ...s, attachments: [...(s.attachments || []),
        { ...a, dataUrl: a.kind === 'image' ? dataUrl : '' }] }))
    } catch (err) {
      status.set('附件失败 · ' + String((err && err.message) || err).slice(0, 60))
    }
  }
  status.set('就绪')
}

function removeAttachment(sid, id) {
  patch(sid, (s) => ({ ...s, attachments: (s.attachments || []).filter((a) => a.id !== id) }))
}

/* ---- settings ------------------------------------------------------- */
function updateSetting(key, value) {
  const next = { ...cfg(), [key]: value }
  settingsValues.set(next)
  settingsDirty.set(true)
  if (key === 'effort') effort.set(value)
  if (key === 'tool_policy') toolPolicy.set(value)
  if (key === 'view_mode') view.set(value)
  if (key === 'brand_theme') setPalette(value)
  if (key === 'font_scale') themeTick.set(themeTick.get() + 1)
}

async function saveSettings() {
  if (!ctxRef) return
  status.set('正在保存设置…')
  try {
    const r = await api('/settings', { method: 'POST', body: { values: cfg() } })
    settingsValues.set(r.values || {})
    settingsSaved.set(r.values || {})
    settingsDirty.set(false)
    applyUiFromSettings(r.values || {})
    status.set('设置已保存 · 下一条消息生效')
  } catch (err) {
    status.set('保存失败 · ' + String((err && err.message) || err).slice(0, 60))
  }
}

async function resetSettings() {
  if (!ctxRef) return
  try {
    const r = await api('/settings/reset', { method: 'POST', body: {} })
    settingsValues.set(r.values || {})
    settingsSaved.set(r.values || {})
    settingsDirty.set(false)
    applyUiFromSettings(r.values || {})
    status.set('已恢复默认设置')
  } catch (err) {
    status.set('恢复失败 · ' + String((err && err.message) || err).slice(0, 60))
  }
}

/* ---- upgrade -------------------------------------------------------- */
async function checkUpgrade() {
  if (!ctxRef) return
  status.set('正在检查 Claude Code 更新…')
  try {
    const r = await api('/upgrade/check')
    upgrade.set({ ...upgrade.get(), checked: true, current: r.current,
                  latest: r.latest, available: r.update_available,
                  installDir: r.install_dir || upgrade.get().installDir })
    status.set(r.update_available
      ? `有更新 · ${r.latest}` : `已是最新版本 · ${r.current}`)
  } catch (err) {
    upgrade.set({ ...upgrade.get(), error: String((err && err.message) || err) })
    status.set('检查更新失败（可能是网络不可达）')
  }
}

function stopUpgradePoll() {
  if (upgradeTimer) {
    try { upgradeTimer() } catch (_) { /* ignore */ }
    upgradeTimer = null
  }
}

async function pollUpgrade() {
  if (!ctxRef) return
  try {
    const r = await api('/upgrade/status')
    upgrade.set({ ...upgrade.get(), running: !!r.running, log: r.log || [],
                  exit: r.exit, before: r.before || upgrade.get().current,
                  after: r.after, error: r.error || '', method: r.method })
    if (!r.running) {
      backend.set({ ...backend.get(), version: r.after || backend.get().version,
                    claudeOk: !r.install_problem,
                    claudeProblem: r.install_problem || '' })
      cliInfo.set({ ...cliInfo.get() })
      stopUpgradePoll()
      status.set(r.error
        ? '升级未完成 · ' + String(r.error).slice(0, 70)
        : (r.exit === 0 ? `升级完成 · ${r.after || ''}` : '升级结束（查看日志）'))
    }
  } catch (err) {
    stopUpgradePoll()
    status.set('升级状态查询失败')
  }
}

async function doUpgrade(method) {
  if (!ctxRef || upgrade.get().running) return
  try {
    await api('/upgrade', { method: 'POST', body: { method: method || 'npm' } })
    upgrade.set({ ...upgrade.get(), running: true, log: [], exit: null, error: '' })
    status.set('正在升级 Claude Code…')
    stopUpgradePoll()
    if (ctxRef) upgradeTimer = ctxRef.setInterval(() => void pollUpgrade(), 900)
    setTimeout(() => void pollUpgrade(), 400)
  } catch (err) {
    status.set('升级启动失败 · ' + String((err && err.message) || err).slice(0, 60))
  }
}

/* ------------------------------------------------------------------ */
/* Rendering helpers                                                    */
/* ------------------------------------------------------------------ */
function richText(text) {
  const parts = String(text || '').split('```')
  return parts.map((part, i) => (i % 2 === 1
    ? h('pre', { key: i, style: S.code }, part.replace(/^[a-zA-Z0-9+#-]+\n/, ''))
    : h('span', { key: i, style: { whiteSpace: 'pre-wrap' } }, part)))
}

/** Rebuild the visible thread: exactly one thinking block per turn, always
 *  placed above that turn's answer. This is what stops a finished reply from
 *  keeping the previous round's chain glued underneath it. */
function groupMessages(messages) {
  const buckets = new Map()
  const order = []
  let turn = 0
  for (const m of messages || []) {
    // Messages restored from older builds have no turn stamp; derive one so
    // their chain still collapses into a single row.
    if (m.role === 'user') turn += 1
    const t = m.turn == null ? turn : m.turn
    const key = 'g' + t
    if (!buckets.has(key)) {
      buckets.set(key, { head: [], think: [], tail: [] })
      order.push(key)
    }
    const b = buckets.get(key)
    if (m.role === 'thinking') b.think.push(m)
    else if (m.role === 'user' || !b.think.length) b.head.push(m)
    else b.tail.push(m)
  }
  const out = []
  for (const k of order) {
    const b = buckets.get(k)
    out.push(...b.head)
    if (b.think.length) {
      out.push({
        key: 'th-' + k,
        role: 'thinking',
        // Delta chunks are cut mid-sentence every ~48 chars, so they must be
        // stitched back without inserting breaks.
        text: b.think.map((m) => m.text || '').join(''),
        streaming: b.think.some((m) => m.streaming)
      })
    }
    out.push(...b.tail)
  }
  return out
}

function MessageItem({ msg }) {
  const [open, setOpen] = useState(false)
  const [thinkOpen, setThinkOpen] = useState(null)
  const v = useValue(view)
  useValue(themeTick)

  if (msg.role === 'user') {
    return h('div', { style: S.userWrap },
      h('div', { style: S.userBubble },
        msg.text,
        (msg.attachments || []).length
          ? h('div', { style: { marginTop: '6px', display: 'flex', gap: '5px', flexWrap: 'wrap' } },
              ...msg.attachments.map((a, i) =>
                h('span', { key: i, style: { fontSize: '0.64rem', padding: '2px 6px',
                                             borderRadius: '5px', background: S.badge.background,
                                             color: P.white } },
                  (a.kind === 'image' ? '图片 · ' : a.kind === 'video' ? '视频 · ' : '文件 · ') + a.name)))
          : null))
  }
  if (msg.role === 'assistant') {
    return h('div', { style: S.assistant },
      ...richText(msg.text),
      msg.streaming ? h('span', { style: { opacity: 0.6 } }, '▍') : null)
  }
  if (msg.role === 'error') {
    return h('div', { style: S.err }, msg.text)
  }
  if (msg.role === 'log') {
    return v === 'verbose' ? h('div', { style: S.note }, '› ' + String(msg.text || '').slice(0, 500)) : null
  }
  if (msg.role === 'thinking') {
    const text = String(msg.text || '')
    const chars = text.length
    const live = !!msg.streaming
    const isOpen = thinkOpen === null ? live : thinkOpen
    return h('div', { style: S.think },
      h('div', { style: S.thinkHead, onClick: () => setThinkOpen(!isOpen) },
        h(ClaudeMark, { size: 12, color: P.accent }),
        h('span', {}, live ? '正在思考…' : '思考过程'),
        chars ? h('span', { style: { color: P.faint, fontSize: '0.68rem' } },
          chars + ' 字') : null,
        h('span', { style: { flex: 1 } }),
        h(Chevron, { open: isOpen, color: P.faint })),
      isOpen ? h('div', { style: S.thinkBody }, text) : null)
  }
  if (msg.role === 'tool') {
    const detail = msg.text !== undefined
      ? String(msg.text)
      : (() => { try { return JSON.stringify(msg.input || {}, null, 2) } catch (_) { return '' } })()
    const isResult = msg.name === 'result'
    return h('div', { style: S.card },
      h('div', { style: S.cardHead, onClick: () => setOpen(!open) },
        h('span', { style: { color: P.faint } }, open ? '▾' : '▸'),
        h('span', { style: { color: isResult ? P.green : P.accent2, fontFamily: P.mono } },
          isResult ? '↳' : '›'),
        h('span', { style: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
          msg.hint || msg.name || 'tool'),
        h('span', { style: { ...S.optTag, color: isResult ? P.green : P.faint } },
          isResult ? '已完成' : (msg.state === 'running' ? '执行中' : '调用')),
        h('span', { style: S.hint }, open ? '收起' : '详情')),
      open ? h('div', { style: S.cardBody }, detail.slice(0, 4000) || '(无参数)') : null)
  }
  return null
}

const TRACE_LABEL = {
  reasoning: '思考', tool: '工具调用', result: '工具返回',
  usage: '用量', log: '日志', note: '节点'
}

function TracePanel({ session }) {
  const [open, setOpen] = useState(false)
  useValue(themeTick)
  const c = cfg()
  if (c.show_thinking_chain === false) return null
  const turn = session.turn || 0
  const traces = (session.traces || []).filter((t) => (t.turn || 0) === turn)
  const last = traces[traces.length - 1]
  if (!last) return null
  const items = last.items || []
  const chars = items.filter((i) => i.kind === 'reasoning')
    .reduce((n, i) => n + (i.chars || (i.text || '').length), 0)
  const tools = items.filter((i) => i.kind === 'tool').length
  const results = items.filter((i) => i.kind === 'result').length
  // A round that only thought (no tools at all) is rendered as the inline
  // thinking row instead — one chain, not two competing cards.
  if (!tools && !results) return null
  const elapsed = Math.max(0, Math.round(((last.ended || Date.now()) - last.started) / 1000))
  return h('div', { style: S.trace },
    h('div', { style: S.traceHead, onClick: () => setOpen(!open) },
      h(ClaudeMark, { size: 12, color: P.accent }),
      h('span', {}, `思考链 · ${chars} 字思考 · ${tools} 次工具调用 · ${results} 次返回 · ${elapsed}s`),
      h('span', { style: { ...S.hint, marginLeft: 'auto', flex: 'none' } },
        last.closed ? (last.error ? '异常结束' : '已完成') : '进行中'),
      h('span', { style: { color: P.faint } }, open ? '▾' : '▸')),
    open ? h('div', { style: S.traceBody },
      items.length
        ? h('div', {}, ...items.map((it, i) =>
            h('div', { key: i, style: S.traceRow },
              h('span', { style: S.traceKind }, TRACE_LABEL[it.kind] || it.kind),
              h('span', { style: S.traceText },
                it.name ? `[${it.name}] ${it.text || ''}` : (it.text || '')))))
        : h('div', { style: S.note }, '本轮没有产生上游思考或工具调用事件。')) : null)
}

/** Resolve the current per-session model into a short, displayable label. */
function modelLabel(session, b) {
  const id = session.model || b.recommended || ''
  const i = id.indexOf('/')
  const slug = i < 0 ? id : id.slice(0, i)
  const name = i < 0 ? id : id.slice(i + 1)
  const g = (b.groups || []).find((x) => x.slug === slug)
  return { id, group: g ? g.name : slug, name: name || '选择模型' }
}

/** Group-level probe hint (one model tested per group), with real reason. */
function groupStatus(g) {
  if (g.online === true) return { text: '● 在线', color: P.green, detail: '探测通过 · HTTP 200' }
  if (g.online !== false) return { text: '○ 未探测', color: P.faint, detail: '未执行在线探测' }
  const d = String(g.detail || '')
  const code = Number(g.status || 0)
  let text = '○ 离线'
  if (/credits|balance|积分|余额/i.test(d)) text = '○ 需积分'
  else if (/不支持模型|model_not_found|not_found/i.test(d)) text = '○ 模型名不兼容'
  else if (code === 401 || code === 403 || /unauthor|未授权/i.test(d)) text = '○ 凭据无效'
  else if (code === 502 || code === 503 || /connect|拒绝|refused|10061|timeout|timed out/i.test(d)) text = '○ 服务未启动'
  return { text, color: P.faint,
           detail: (code ? 'HTTP ' + code + ' · ' : '') + (d || '在线探测未通过') }
}

/** Bottom-right model dropdown (official Claude Code desktop placement). */
function ModelPicker({ session }) {
  const b = useValue(backend)
  const open = useValue(modelPicker)
  const q = useValue(modelQuery)
  const [hover, setHover] = useState('')
  const cur = modelLabel(session, b)
  const needle = q.trim().toLowerCase()
  useValue(themeTick)

  const groups = (b.groups || []).map((g) => {
    const groupHit = (g.name || '').toLowerCase().includes(needle) ||
                     (g.slug || '').toLowerCase().includes(needle)
    const models = (g.models || []).filter((m) => groupHit || m.toLowerCase().includes(needle))
    return { ...g, models }
  }).filter((g) => g.models.length)

  const choose = (slug, name) => {
    const id = slug + '/' + name
    patch(session.id, (s) => ({ ...s, model: id }))
    modelPicker.set(false)
    modelQuery.set('')
    status.set('模型已切换 · ' + id)
  }

  return h('div', { style: S.pickWrap },
    open ? h('div', { style: S.overlay, onClick: () => modelPicker.set(false) }) : null,
    h('button', {
      style: { ...S.pickBtn,
               ...(open ? { background: P.bg2, borderColor: P.line }
                        : (hover === '__btn' ? { background: P.bg2 } : {})) },
      onMouseEnter: () => setHover('__btn'),
      onMouseLeave: () => setHover(''),
      title: '选择模型 · Hermes Desktop 中全部 ' + (b.total || 0) + ' 个模型',
      onClick: () => { modelQuery.set(''); modelPicker.set(!open) }
    },
      h('span', { style: S.pickName }, cur.name),
      h(Chevron, { open, size: 10, color: P.faint })),
    open ? h('div', { style: S.pop },
      h('div', { style: S.popHead },
        h('div', { style: S.popTitle }, '选择模型 · Hermes Desktop'),
        h('input', {
          style: S.popSearch, value: q, placeholder: '搜索模型或提供商…',
          onChange: (e) => modelQuery.set(e.target.value)
        })),
      h('div', { style: S.popList },
        ...groups.map((g) => {
          const gs = groupStatus(g)
          return h('div', { key: g.slug },
            h('div', { style: S.grp },
              h('span', {}, g.name),
              h('span', { style: { color: gs.color }, title: gs.detail }, gs.text),
              h('span', { style: { marginLeft: 'auto' } }, (g.models || []).length + ' 个')),
            ...g.models.map((m) => {
              const id = g.slug + '/' + m
              const on = id === cur.id
              const hot = hover === id
              return h('div', {
                key: id,
                style: { ...S.opt,
                         ...(on ? { background: P.bg2 } : hot ? { background: 'rgba(31,29,27,0.045)' } : {}) },
                onMouseEnter: () => setHover(id),
                onMouseLeave: () => setHover(''),
                onClick: () => choose(g.slug, m)
              },
                h('span', { style: { ...S.optName, fontWeight: on ? 600 : 400 } }, m),
                on ? h('span', { style: { color: P.accent, fontSize: '0.78rem', lineHeight: 1 } }, '✓') : null)
            }))
        }),
        !groups.length ? h('div', { style: { ...S.note, padding: '10px 8px' } },
          '没有匹配的模型，试试其他关键词。') : null),
      h('div', { style: S.popFoot },
        h('div', {}, `共 ${b.total || 0} 个模型 · 凭据来自 Hermes`),
        h('div', { style: { marginTop: '2px' } },
          '状态为组级探测（每组仅试 1 个模型），仅供参考；标记异常仍可选择'))) : null)
}

function Toolbar({ session }) {
  const b = useValue(backend)
  const st = useValue(status)
  const v = useValue(view)
  const ef = useValue(effort)
  const tp = useValue(toolPolicy)
  const up = useValue(upgrade)
  const pending = useValue(approvals)
  const [more, setMore] = useState(false)
  useValue(settingsValues)
  const cur = modelLabel(session, b)
  useValue(themeTick)
  return h('div', { style: S.barWrap },
    h('div', { style: S.bar },
      h('span', { style: S.barTitle, title: session.title || '新会话' },
        session.title || '新会话'),
      h('span', { style: { flex: 1 } }),
      h('button', {
        style: S.ctlBtn,
        title: '当前模型 · 点击切换',
        onClick: () => modelPicker.set(true)
      }, h('span', { style: { color: P.text, fontWeight: 600 } }, cur.name),
         h(Chevron, { open: false, size: 10, color: P.faint })),
      pending.length
        ? h('button', {
            style: { ...S.ctlBtn, color: P.accent2 },
            title: '有待审批的操作，点此允许第一个（Y）',
            onClick: () => decideFirst('allow')
          }, `待审批 ${pending.length}`)
        : null,
      h('button', {
        style: { ...S.ctlBtn, ...(more ? { background: P.bg2 } : {}) },
        title: '更多会话参数（工具 / 强度 / 视图 / 权限 / 目录 / 审批开关）',
        onClick: () => setMore(!more)
      }, '更多', h(Chevron, { open: more, size: 9, color: P.faint })),
      h('button', { style: S.ctlBtn, title: '重新读取 Hermes 模型目录',
                    onClick: () => void loadBackend(true) }, '刷新'),
      h('button', { style: S.ctlBtn, title: '打开插件设置（CLI 全量配置 / 升级 / 功能矩阵）',
                    onClick: () => openSettings() }, '设置'),
      h('button', { style: S.ctlBtn,
                    title: `Claude Code ${b.version || ''} · 点击一键升级`,
                    onClick: () => { openSettings('升级与诊断'); void checkUpgrade() } },
        up.running ? '升级中…' : '升级')),
    more
      ? h('div', { style: S.barMore },
          h('span', { style: S.label }, '目录'),
          h('input', {
            style: { ...S.ctl, width: '150px' }, value: session.cwd || '',
            title: 'Claude Code 的工作目录',
            placeholder: b.defaultCwd || '~/projects',
            onChange: (e) => patch(session.id, (x) => ({ ...x, cwd: e.target.value }))
          }),
          h('select', { style: S.ctl, value: tp, title: '工具调用方式',
                        onChange: (e) => updateSetting('tool_policy', e.target.value) },
            h('option', { value: 'auto' }, '工具·自动'),
            h('option', { value: 'describe' }, '工具·仅描述'),
            h('option', { value: 'off' }, '工具·关闭')),
          h('select', { style: S.ctl, value: ef, title: '推理强度',
                        onChange: (e) => updateSetting('effort', e.target.value) },
            h('option', { value: '' }, '强度·默认'),
            h('option', { value: 'low' }, '低'),
            h('option', { value: 'medium' }, '中'),
            h('option', { value: 'high' }, '高'),
            h('option', { value: 'xhigh' }, '极高'),
            h('option', { value: 'max' }, '最大')),
          h('select', { style: S.ctl, value: v, title: '消息显示详细程度',
                        onChange: (e) => updateSetting('view_mode', e.target.value) },
            h('option', { value: 'normal' }, '标准视图'),
            h('option', { value: 'verbose' }, '详细视图'),
            h('option', { value: 'compact' }, '精简视图')),
          h('select', {
            style: S.ctl, value: permMode(),
            title: '权限模式 · 输入框 Shift+Tab 循环切换 · ⌘/Ctrl+Shift+P',
            onChange: (e) => void persistSetting('permission_mode', e.target.value)
          },
            ...PERMISSION_MODES.map((m) =>
              h('option', { key: m, value: m }, '权限·' + (PERMISSION_LABELS[m] || m)))),
          h('button', {
            style: { ...S.ctlBtn, ...(approvalOn() ? {} : { color: P.red }) },
            title: '插件内审批开关 · ⌘/Ctrl+Shift+B',
            onClick: toggleApprovalMode
          }, approvalOn() ? '审批·开' : '审批·关'),
          h('span', { style: S.barStatus }, `${st} · ${b.total || 0} 个模型`))
      : null)
}

/** Real permission prompts from Claude Code's --permission-prompt-tool MCP bridge. */
function ApprovalPanel() {
  const list = useValue(approvals)
  const [, tick] = useState(0)
  const cardRef = useRef(null)
  useValue(themeTick)

  useEffect(() => {
    if (!list.length) return
    if (cardRef.current && cardRef.current.focus) {
      try { cardRef.current.focus() } catch (_) { /* host may block focus */ }
    }
    const t = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [list.length, list.length ? list[0].id : ''])

  if (!list.length) return null
  const shown = list.slice(0, 2)
  return h('div', { style: S.apprWrap },
    ...shown.map((a, i) => {
      const left = Math.max(0, Math.ceil((Number(a.deadline || 0) * 1000 - Date.now()) / 1000))
      let raw = ''
      try { raw = JSON.stringify(a.input || {}, null, 2) } catch (_) { raw = String(a.input) }
      return h('div', {
        key: a.id,
        ref: i === 0 ? cardRef : undefined,
        tabIndex: 0,
        style: S.apprCard,
        onKeyDown: (e) => {
          const k = String(e.key || '').toLowerCase()
          if (k === 'y') { e.preventDefault(); void decideApproval(a.id, 'allow') }
          else if (k === 'a') { e.preventDefault(); void decideApproval(a.id, 'always_allow') }
          else if (k === 'n' || k === 'escape') {
            e.preventDefault(); void decideApproval(a.id, 'deny')
          }
        }
      },
        h('div', { style: S.apprHead }, '授权请求 · Claude Code',
          h('span', { style: S.apprCount }, `${i + 1} / ${list.length} 待审批`)),
        h('div', { style: S.apprBody },
          h('div', { style: S.apprTool }, a.tool_name || '未知工具'),
          h('div', { style: S.apprInput }, (raw || '').slice(0, 900) || '(无参数)'),
          h('div', { style: S.apprMeta },
            h('span', {}, `⏱ ${left}s 后自动拒绝`),
            h('span', {}, a.tool_use_id ? 'ID ' + String(a.tool_use_id).slice(0, 16) : ''))),
        h('div', { style: S.apprActions },
          h('button', { style: { ...S.apprBtn, ...S.apprAllow },
                        onClick: () => void decideApproval(a.id, 'allow') }, '✓ 允许  Y'),
          h('button', { style: { ...S.apprBtn, ...S.apprAlways },
                        onClick: () => void decideApproval(a.id, 'always_allow') }, '✓✓ 始终允许  A'),
          h('button', { style: { ...S.apprBtn, ...S.apprDeny },
                        onClick: () => void decideApproval(a.id, 'deny') }, '✕ 拒绝  N'),
          h('span', { style: S.apprKeys }, 'Esc 拒绝')))
    }),
    list.length > 2
      ? h('div', { style: { ...S.apprCard, padding: '7px 11px',
                            fontSize: '0.66rem', color: P.dim } },
          `另有 ${list.length - 2} 个操作等待审批…`)
      : null)
}

function Composer({ session }) {
  const d = useValue(draft)
  const isBusy = useValue(busy)
  const b = useValue(backend)
  const [hoverAttach, setHoverAttach] = useState(false)
  useValue(settingsValues)
  const cwd = session.cwd || b.defaultCwd || ''
  const cwdShort = cwd.split(/[\\/]/).filter(Boolean).pop() || '工作目录'
  const attachments = session.attachments || []
  const taRef = useRef(null)
  useValue(themeTick)
  useEffect(() => { growTextarea(taRef.current) }, [d, session.id])
  return h('div', { style: S.composer },
    h('div', { style: S.composerBox },
      attachments.length
        ? h('div', { style: S.attachBar },
            ...attachments.map((a) =>
              h('span', { key: a.id, style: S.attachChip, title: a.path },
                a.dataUrl && a.kind === 'image'
                  ? h('img', { src: a.dataUrl, style: S.thumb, alt: a.name })
                  : h('span', { style: { color: P.accent2 } },
                      a.kind === 'video' ? '▶' : a.kind === 'audio' ? '♪' : '▤'),
                h('span', { style: { maxWidth: '128px', overflow: 'hidden',
                                     textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, a.name),
                h('span', { style: { color: P.faint } },
                  (a.size > 1024 * 1024
                    ? (a.size / 1024 / 1024).toFixed(1) + 'MB'
                    : Math.max(1, Math.round(a.size / 1024)) + 'KB')),
                h('button', { style: { ...S.del, color: P.faint }, title: '移除附件',
                              onClick: () => removeAttachment(session.id, a.id) }, '×'))))
        : null,
      h('textarea', {
        style: S.ta, value: d, rows: 1,
        ref: (el) => { taRef.current = el; growTextarea(el) },
        placeholder: '回复…',
        onChange: (e) => { draft.set(e.target.value); growTextarea(e.target) },
        onKeyDown: (e) => {
          if (e.key === 'Tab' && e.shiftKey) {
            e.preventDefault()
            cyclePermissionMode()
            return
          }
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent?.isComposing) {
            e.preventDefault()
            void sendMessage()
          }
        }
      }),
      h('div', { style: S.foot },
        h('button', {
          style: { ...S.iconBtn, ...(hoverAttach ? { background: P.bg3 } : {}) },
          title: '上传附件（图片、视频、文件）',
          onMouseEnter: () => setHoverAttach(true),
          onMouseLeave: () => setHoverAttach(false),
          onClick: () => { if (fileInputRef && fileInputRef.current) fileInputRef.current.click() }
        }, h(Paperclip, { size: 14 })),
        h('input', {
          type: 'file', multiple: true, ref: (el) => { fileInputRef = { current: el } },
          style: { display: 'none' },
          onChange: (e) => {
            const files = e.target.files
            if (files && files.length) void addFiles(files, session.id)
            e.target.value = ''
          }
        }),
        h('span', { style: { flex: 1 } }),
        h(ModelPicker, { session }),
        isBusy
          ? h('button', { style: S.stop, title: '停止生成（Esc）',
                          onClick: () => void stopRun() },
              h('svg', { width: 11, height: 11, viewBox: '0 0 24 24', 'aria-label': '停止' },
                h('rect', { x: 5, y: 5, width: 14, height: 14, rx: 2.5,
                            fill: 'currentColor' })))
          : h('button', { style: S.send, title: '发送（Enter）',
                          onClick: () => void sendMessage() },
              h(ArrowUp, { size: 15 })))))
}

/** One row of the CLI history list: two lines, hover menu like the desktop app. */
function HistRow({ item, active }) {
  const [hover, setHover] = useState(false)
  const renaming = useValue(histRenaming)
  const [draftTitle, setDraftTitle] = useState(item.title || '')
  useValue(themeTick)
  if (renaming === item.id) {
    return h('div', { style: S.hrow },
      h('input', {
        autoFocus: true, style: S.renameInput, value: draftTitle,
        placeholder: '会话名称（留空恢复自动标题）',
        onChange: (e) => setDraftTitle(e.target.value),
        onKeyDown: (e) => {
          if (e.key === 'Enter') void renameHistory(item.id, draftTitle)
          if (e.key === 'Escape') histRenaming.set(null)
        },
        onBlur: () => void renameHistory(item.id, draftTitle)
      }),
      h('button', { style: S.miniBtn, title: '恢复 Claude 自动生成的标题',
                    onClick: () => void renameHistory(item.id, '') }, '自动'))
  }
  return h('div', {
    style: { ...S.hrow, ...(active || hover ? { background: P.bg3 } : {}) },
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    onClick: () => void openHistorySession(item)
  },
    h('div', { style: { flex: 1, minWidth: 0 } },
      h('div', { style: { ...S.hrowTitle, color: active ? P.text : P.dim } },
        item.pinned ? h('span', { style: { color: P.accent } }, '★') : null,
        item.archived ? h('span', { style: { color: P.faint } }, '⌸') : null,
        item.title || '未命名会话'),
      h('div', { style: S.hrowMeta },
        (item.project_label || '') + ' · ' + relTime(item.updated) +
        (item.turns ? ' · ' + item.turns + ' 轮' : ''))),
    item.unread
      ? h('span', { style: S.unreadDot, title: '未读' })
      : null,
    h('button', {
      style: { ...S.hrowMenu, opacity: hover || active ? 1 : 0 },
      title: '重命名 / 归档 / 删除',
      onClick: (e) => {
        e.stopPropagation()
        const r = e.currentTarget.getBoundingClientRect()
        const height = 430
        const top = Math.min(r.bottom + 4, Math.max(8, (window.innerHeight || 900) - height))
        histMenu.set({ id: item.id, item, sub: null,
                       x: Math.max(8, r.right - 214), y: top })
        histConfirm.set(null)
      }
    }, '⋯'))
}

function CcApp() {
  const list = useValue(sessions)
  const active = useValue(activeId)
  const b = useValue(backend)
  const st = useValue(status)
  const chan = useValue(channel)
  const hs = useValue(history)
  const tab = useValue(histTab)
  const menu = useValue(histMenu)
  const confirmId = useValue(histConfirm)
  const mo = useValue(mobileOpen)
  const ml = useValue(mobileState)
  const session = list.find((s) => s.id === active) || list[0]
  const scrollRef = useRef(null)
  useValue(themeTick)
  const lang = useValue(langAtom)
  const scale = Number(cfg().font_scale || 1)

  useEffect(() => {
    if (booted || !ctxRef) return
    booted = true
    void loadBackend(false)
    void loadHistory(false)
    for (const row of sessions.get()) {
      if (row.fromHistory && !(row.messages || []).length) void refillHistorySession(row)
    }
    const t = setTimeout(() => void loadBackend(true), 1500)
    const t2 = setTimeout(() => void refreshApprovals(), 1800)
    return () => { clearTimeout(t); clearTimeout(t2) }
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [session && session.messages.length, active])

  const needle = String(hs.q || '').trim().toLowerCase()
  const match = (v) => !needle || String(v || '').toLowerCase().includes(needle)
  const localRows = list.filter((s) => !s.fromHistory && match(s.title))
  const remoteRows = (hs.items || []).filter((it) =>
    match(it.title) || match(it.project_label) || match(it.cwd) || match(it.last_prompt))
  const activeResume = (list.find((s) => s.id === active) || {}).resumeId || null

  if (!session) return h('div', { style: S.empty }, '没有会话')

  const mi = (label, onClick, opts) => h('button', {
    key: label,
    style: { ...S.menuItem, ...((opts && opts.danger) ? { color: P.red } : {}) },
    onMouseEnter: (e) => { e.currentTarget.style.background = P.bg3 },
    onMouseLeave: (e) => { e.currentTarget.style.background = 'transparent' },
    onClick: (e) => { e.stopPropagation(); onClick() }
  }, label)
  const sep = (k) => h('div', { key: 'sp' + k, style: S.menuSep })

  return h('div', { style: { ...S.root, fontSize: `calc(0.78rem * ${scale})` } },
    h('div', { style: S.side },
      h('div', { style: S.sideHead },
        h(ClaudeMark, { size: 18 }),
        h('span', { style: S.brand }, 'Claude Code'),
        h('span', { style: S.badge }, 'Desktop')),
      h('div', { style: S.sideTools },
        h('button', { style: S.newBtn, title: '新建会话',
                      onClick: () => newSession() }, '＋ 新建会话'),
        h('input', {
          style: S.histSearch, placeholder: '搜索会话…', value: hs.q,
          onChange: (e) => history.set({ ...history.get(), q: e.target.value })
        }),
        h('div', { style: S.histTabs },
          ...[['active', '会话'], ['archived', '已归档'], ['trash', '回收站']].map(([key, label]) =>
            h('button', {
              key,
              style: { ...S.histTabBtn, ...(tab === key
                ? { background: P.bg, color: P.text, borderColor: P.line } : {}) },
              onClick: () => setHistTab(key)
            }, label + (key === 'archived' && hs.archived ? ' ' + hs.archived
                      : key === 'trash' && hs.trash ? ' ' + hs.trash : '')))),
        tab !== 'trash'
          ? h('div', { style: S.histHead },
              h('span', {}, tab === 'archived' ? '已归档会话' : 'Claude Code 历史会话'),
              h('span', { style: { flex: 1 } }),
              hs.loading
                ? h('span', {}, '读取中…')
                : h('button', { style: S.miniBtn, title: '重新扫描 ~/.claude/projects',
                                onClick: () => void loadHistory(true) }, '刷新'))
          : null),
      h('div', { style: S.sideList },
        hs.error
          ? h('div', { style: S.histErr }, hs.error)
          : null,
        tab === 'trash'
          ? ((hs.trashItems || []).length
              ? [
                  ...(hs.trashItems || []).map((item) =>
                    h('div', { key: item.id, style: S.hrow },
                      h('div', { style: { flex: 1, minWidth: 0 } },
                        h('div', { style: S.hrowTitle }, item.title || item.id),
                        h('div', { style: S.hrowMeta }, '删除于 ' + relTime(item.deleted))),
                      h('button', { style: S.miniBtn, title: '恢复到原项目',
                                    onClick: () => void restoreHistory(item) }, '恢复'),
                      h('button', {
                        style: { ...S.miniBtn, color: P.red },
                        title: '彻底删除，不可恢复',
                        onClick: () => { if (confirmId === item.id) void purgeHistory(item.id); else histConfirm.set(item.id) }
                      }, confirmId === item.id ? '确认' : '删除'))),
                  (hs.trashItems || []).length > 1
                    ? h('button', { style: { ...S.miniBtn, width: '100%', marginTop: '6px', color: P.red },
                                    onClick: () => { if (confirmId === '__all__') void purgeHistory(null); else histConfirm.set('__all__') } },
                        confirmId === '__all__' ? '再次点击确认清空回收站' : '清空回收站')
                    : null
                ]
              : h('div', { style: S.histEmpty }, '回收站是空的'))
          : [
              /* plugin-owned sessions first — they are the ones being typed into */
              localRows.length
                ? h('div', { style: S.histSect }, '当前会话')
                : null,
              ...localRows.map((s) =>
                h('div', {
                  key: s.id,
                  style: { ...S.sess, background: s.id === active ? P.bg3 : 'transparent' },
                  onClick: () => activeId.set(s.id)
                },
                  h('span', { style: { ...S.sessTitle, color: s.id === active ? P.text : P.dim } }, s.title),
                  h('button', {
                    style: S.del, title: '从列表移除（不删除 CLI 历史）',
                    onClick: (e) => { e.stopPropagation(); deleteSession(s.id) }
                  }, '×'))),
              h('div', { style: S.histSect },
                tab === 'archived' ? '已归档 · 点击恢复' : '历史会话 · ' + remoteRows.length,
                h('span', { style: { flex: 1 } }),
                !hs.loaded && !hs.loading
                  ? h('button', { style: S.miniBtn, onClick: () => void loadHistory(true) }, '载入')
                  : null),
              ...remoteRows.map((item) => h(HistRow, { key: item.id, item,
                                                       active: item.id === activeResume })),
              !hs.loading && !remoteRows.length
                ? h('div', { style: S.histEmpty },
                    hs.loaded
                      ? (tab === 'archived' ? '没有归档的会话' : '这个项目还没有历史会话')
                      : '点击「载入」读取 CLI 历史')
                : null
            ]),
      h('div', { style: S.sideFoot },
        h('div', {}, b.ok
          ? (b.claudeOk ? '● Claude Code 已就绪' : '● 已连接 · CLI 安装损坏')
          : '○ 后端未连接'),
        h('div', { style: { marginTop: '3px' } },
          b.claudeOk ? (b.version || '').slice(0, 44) : '安装需修复（设置 → 升级与诊断）'),
        b.error ? h('div', { style: { marginTop: '4px', color: P.red } }, '后端未就绪 · 见主区域') : null,
        b.ok && !b.claudeOk
          ? h('div', { style: { marginTop: '4px', color: P.red } }, b.claudeProblem || '')
          : null,
        h('div', { style: { marginTop: '4px' } }, st),
        h('button', { style: { ...S.miniBtn, width: '100%', marginTop: '6px' },
                      title: '用手机在同一 Wi-Fi 下打开同样的界面',
                      onClick: () => void showMobile() }, '手机访问'),
        h('div', { style: { display: 'flex', gap: '4px', marginTop: '5px' } },
          LANGS.map((id) => h('button', {
            key: id,
            title: id === 'en' ? 'English' : '中文',
            style: { ...S.miniBtn, flex: 1, padding: '2px 0',
                     background: lang === id ? P.bg3 : P.bg,
                     color: lang === id ? P.text : P.faint,
                     fontWeight: lang === id ? 700 : 400 },
            onClick: () => setLang(id)
          }, id === 'en' ? 'English' : '中文'))))),
    h('div', { style: S.main },
      h(Toolbar, { session }),
      session.fromHistory
        ? h('div', { style: S.histBanner },
            '来自 Claude Code 历史记录 · ' + String(session.resumeId || '').slice(0, 8) +
            ' · 继续发送会接着这个会话（--resume），不会新建')
        : null,
      h('div', { style: S.stream, ref: scrollRef },
        h(TracePanel, { session }),
        session.messages.length === 0
          ? (b.error
              ? h('div', { style: S.empty },
                  h(ClaudeMark, { size: 30 }),
                  h('div', { style: { fontWeight: 650, color: P.red, marginTop: '6px' } },
                    '插件后端未就绪'),
                  h('div', { style: { maxWidth: '520px', lineHeight: 1.7, marginTop: '4px' } },
                    b.error),
                  b.raw ? h('div', { style: { fontSize: '0.66rem', marginTop: '6px', color: P.faint } },
                           '原始错误：' + b.raw) : null,
                  h('button', {
                    style: { ...S.newBtn, width: 'auto', marginTop: '10px', padding: '6px 16px' },
                    onClick: () => { backend.set({ ...backend.get(), error: '' }); void loadBackend(true) }
                  }, '重新连接'),
                  h('div', { style: { fontSize: '0.66rem', marginTop: '8px', color: P.faint } },
                    '自动尝试过的通道：网关插件接口 → 本机直连（127.0.0.1:47823~47828）。'),
                  h('div', { style: { fontSize: '0.64rem', marginTop: '4px', color: P.faint,
                                      fontFamily: P.mono, wordBreak: 'break-all' } },
                    '当前通道：' + chan))
              : h('div', { style: S.empty },
                  h(ClaudeMark, { size: 42 }),
                  h('div', { style: { fontWeight: 550, color: P.text, marginTop: '10px',
                                     fontSize: '0.95rem' } }, 'Claude Code')))
          : h('div', { style: S.thread }, ...groupMessages(session.messages).map((m) =>
              h(MessageItem, { key: m.key, msg: m })))),
      h(Composer, { session }),
      h(ApprovalPanel, {})),
    menu
      ? h('div', { style: S.menuOverlay,
                   onClick: () => { histMenu.set(null); histConfirm.set(null) } })
      : null,
    menu
      ? h('div', { style: { ...S.menu, left: menu.x, top: menu.y } },
          mi('打开会话', () => void openHistorySession(menu.item)),
          mi('在新标签页中打开', () => openInNewTab(menu.item)),
          mi('在终端中打开', () => void openInTerminal(menu.item)),
          sep(1),
          mi('重命名…', () => { histMenu.set(null); histRenaming.set(menu.id) }),
          mi(menu.item.pinned ? '取消置顶' : '置顶',
             () => void patchFlags(menu.item, { pinned: !menu.item.pinned },
                                   menu.item.pinned ? '已取消置顶' : '已置顶')),
          mi(menu.item.unread ? '标记为已读' : '标记为未读',
             () => void patchFlags(menu.item, { unread: !menu.item.unread },
                                   menu.item.unread ? '已标记为已读' : '已标记为未读')),
          sep(2),
          mi('复制 ID', () => copyHistoryId(menu.item)),
          mi('分支（新建会话）', () => forkHistory(menu.item)),
          mi('导出为 Markdown', () => void exportHistory(menu.item)),
          sep(3),
          mi('移动到项目 ›', () => histMenu.set({ ...menu,
                                                 sub: menu.sub === 'move' ? null : 'move' })),
          mi('外观', () => { histMenu.set(null); openSettings('外观与界面') }),
          mi('帮助', () => openClaudeHelp()),
          sep(4),
          mi(menu.item.archived ? '取消归档' : '归档',
             () => void archiveHistory(menu.item, !menu.item.archived)),
          mi(confirmId === menu.id ? '再次点击确认删除' : '删除（移到回收站）',
             () => {
               if (confirmId === menu.id) void deleteHistory(menu.item)
               else histConfirm.set(menu.id)
             }, { danger: true }))
      : null,
    menu && menu.sub === 'move'
      ? h('div', { style: { ...S.menu, left: menu.x + 182, top: menu.y + 176,
                            width: '212px', maxHeight: '320px', overflowY: 'auto' } },
          ...(hs.projects || []).filter((pr) => pr.slug !== menu.item.project)
            .map((pr) => mi(pr.label + '  (' + pr.count + ')',
                            () => void moveHistory(menu.item, pr.slug, pr.label))),
          (hs.projects || []).some((pr) => pr.slug !== menu.item.project)
            ? null
            : h('div', { style: S.histEmpty }, '没有其它项目'))
      : null,
    mo
      ? h('div', { style: S.modalWrap, onClick: () => mobileOpen.set(false) },
          h('div', { style: S.modal, onClick: (e) => e.stopPropagation() },
            h('div', { style: { fontWeight: 650, fontSize: '0.8rem', marginBottom: '4px' } },
              '手机访问 Claude Code'),
            h('div', { style: { fontSize: '0.68rem', color: P.dim, lineHeight: 1.65 } },
              ml.hint || '手机与电脑连同一个 Wi-Fi，用浏览器打开下面的链接。'),
            ml.loading ? h('div', { style: S.histEmpty }, '正在读取局域网地址…') : null,
            ml.error ? h('div', { style: S.histErr }, ml.error) : null,
            ml.qr
              ? h('div', { style: { display: 'flex', flexDirection: 'column',
                                    alignItems: 'center', margin: '10px 0 4px' } },
                  h('img', { src: ml.qr, alt: '手机访问二维码',
                             style: { width: '148px', height: '148px', background: '#fff',
                                      border: '1px solid ' + P.line, borderRadius: '10px',
                                      padding: '6px' } }),
                  h('div', { style: { fontSize: '0.63rem', color: P.faint, marginTop: '5px' } },
                    '手机相机扫一下即可进入'))
              : null,
            ...(ml.urls || []).map((u) => h('div', { key: u, style: S.urlRow },
              h('code', { style: S.urlCode }, u),
              h('button', { style: S.miniBtn, onClick: () => copyText(u, '已复制手机访问链接') },
                '复制'))),
            (!ml.loading && !ml.error && !(ml.urls || []).length)
              ? h('div', { style: S.histErr },
                  '没有检测到局域网地址。请确认电脑已连 Wi-Fi/网线，或检查 47830 端口是否被占用。')
              : null,
            h('div', { style: { fontSize: '0.63rem', color: P.faint, marginTop: '8px',
                                lineHeight: 1.7 } },
              '访问口令是固定的，重启电脑也不会变；会变的只是前面的 IP。',
              h('div', { style: { marginTop: '3px' } },
                '想让 IP 也不变：登录路由器（通常是 192.168.1.1）给这台电脑做「DHCP 地址保留 / 静态分配」。'),
              h('div', { style: { marginTop: '3px' } },
                '手机端可直接点「允许 / 拒绝」完成工具审批，不用再回电脑。'),
              h('div', { style: { marginTop: '3px' } },
                '手机打不开时，先确认同一 Wi-Fi，再看 Windows 防火墙是否放行入站 47830。')),
            h('button', { style: { ...S.secondary, marginTop: '10px' },
                          onClick: () => mobileOpen.set(false) }, '关闭')))
      : null)
}

function CcChip() {
  const st = useValue(status)
  const b = useValue(backend)
  const chan = useValue(channel)
  const s = getSession(activeId.get())
  const label = (s && s.model ? s.model.split('/').pop() : '未选模型')
  useValue(themeTick)
  useValue(langAtom)
  return h('span', {
    style: { fontSize: '0.66rem', color: P.dim, cursor: 'pointer',
             display: 'inline-flex', alignItems: 'center', gap: '4px' },
    title: 'Claude Code Desktop · ' + st,
    onClick: () => { if (typeof host.navigate === 'function') host.navigate('/claude-code') }
  }, h(ClaudeMark, { size: 13 }), `CC · ${label} · ${b.total || 0} 模型 · ${chan}`)
}

/* ------------------------------------------------------------------ */
/* Settings page: schema-driven, every CLI flag / settings key editable   */
/* ------------------------------------------------------------------ */
const TAB_UPGRADE = '升级与诊断'
const TAB_MATRIX = 'CLI 功能矩阵'

function openSettings(tab) {
  settingsTab.set(tab || '模型与推理')
  if (typeof host.navigate === 'function') {
    host.navigate('/settings?tab=plugins&plugin=' + PLUGIN_ID)
  }
}

function Field({ item, value }) {
  useValue(themeTick)
  const typ = item.type
  const map = item.flag && item.flag !== '__chrome__'
    ? item.flag : (item.path ? 'settings.json → ' + item.path : (item.kind || 'plugin'))
  const label = h('div', { style: S.fieldLabel }, item.label)
  const mapping = h('div', { style: S.fieldMap }, map)
  const help = item.help ? h('div', { style: S.fieldHelp }, item.help) : null

  if (typ === 'switch') {
    const on = !!value
    return h('div', { style: S.field }, label, mapping,
      h('div', { style: S.toggle, onClick: () => updateSetting(item.key, !on) },
        h('span', { style: { ...S.toggleBox, background: on ? P.accent : P.line } },
          h('span', { style: { ...S.toggleDot, left: on ? '15px' : '2px' } })),
        h('span', { style: { fontSize: '0.7rem', color: P.dim } }, on ? '开启' : '关闭')),
      help)
  }
  if (typ === 'select') {
    return h('div', { style: S.field }, label, mapping,
      h('select', { style: S.input, value: value === undefined || value === null ? '' : String(value),
                    onChange: (e) => updateSetting(item.key, e.target.value) },
        ...(item.options || []).map((o) =>
          h('option', { key: o, value: o }, o === '' ? '（默认 / 留空）' : o))),
      help)
  }
  if (typ === 'textarea') {
    return h('div', { style: S.field }, label, mapping,
      h('textarea', {
        style: S.textarea, value: value === undefined || value === null ? '' : String(value),
        placeholder: item.type === 'textarea' ? 'JSON 对象或纯文本…' : '',
        onChange: (e) => updateSetting(item.key, e.target.value)
      }), help)
  }
  if (typ === 'list') {
    const joined = Array.isArray(value) ? value.join('\n') : String(value || '')
    return h('div', { style: S.field }, label, mapping,
      h('textarea', {
        style: { ...S.textarea, minHeight: '64px', fontFamily: P.mono },
        value: joined, placeholder: '每行一项，或用逗号分隔',
        onChange: (e) => updateSetting(item.key, e.target.value.split(/[\n,]/))
      }), help)
  }
  return h('div', { style: S.field }, label, mapping,
    h('input', {
      style: S.input, type: typ === 'number' ? 'number' : 'text',
      value: value === undefined || value === null ? '' : String(value),
      onChange: (e) => updateSetting(item.key,
        typ === 'number' ? Number(e.target.value) : e.target.value)
    }), help)
}

function UpgradePanel() {
  const up = useValue(upgrade)
  const b = useValue(backend)
  const cli = useValue(cliInfo)
  useValue(themeTick)
  return h('div', {},
    h('div', { style: S.setTitle }, 'Claude Code 升级与诊断'),
    h('div', { style: S.setSub },
      '直接调用本机 npm / claude update，升级后自动复核版本并刷新 CLI 能力清单。'),
    h('div', { style: S.infoBox },
      h('div', {}, '当前版本：', h('b', {}, up.current || b.version || '未知')),
      h('div', {}, '最新版本：', h('b', {}, up.latest || (up.checked ? '未获取到' : '未检查'))),
      h('div', {}, '安装目录：', h('code', {}, up.installDir || b.installDir || '')),
      h('div', {}, 'CLI 可执行文件：', h('code', {}, '…\\@anthropic-ai\\claude-code\\bin\\claude.exe')),
      h('div', { style: { color: b.claudeOk ? P.green : P.red } },
        b.claudeOk ? '安装状态：正常（原生二进制已就位）'
                   : '安装状态：损坏 · ' + (b.claudeProblem || '原生二进制缺失')),
      h('div', {}, up.available
        ? '检测到可用更新，点击「一键升级」即可安装。'
        : '本地为 npm 依赖安装，升级执行 npm install @anthropic-ai/claude-code@latest。')),
    h('div', { style: S.setActions },
      h('button', { style: S.secondary, onClick: () => void checkUpgrade() },
        '检查更新'),
      h('button', { style: { ...S.primary, opacity: up.running ? 0.6 : 1 },
                    disabled: !!up.running, onClick: () => void doUpgrade('npm') },
        up.running ? '升级进行中…' : '一键升级（npm）'),
      h('button', { style: S.secondary, disabled: !!up.running,
                    onClick: () => void doUpgrade('cli') },
        '用 claude update'),
      h('button', { style: { ...S.secondary, ...(b.claudeOk ? {} : { color: P.accent2,
                    borderColor: P.accent }) }, disabled: !!up.running,
                    title: '不联网重装，只补跑原生二进制安装脚本并校验',
                    onClick: () => void doUpgrade('repair') },
        '修复安装'),
      h('span', { style: { fontSize: '0.65rem', color: P.faint } },
        up.error ? '错误：' + up.error : (up.exit !== null && up.exit !== undefined
          ? '退出码 ' + up.exit + (up.after ? ' · 新版本 ' + up.after : '') : ''))),
    h('div', { style: { ...S.fieldLabel, margin: '10px 0 5px' } }, '升级日志'),
    h('div', { style: S.log },
      (up.log || []).length ? (up.log || []).join('\n') : '（暂无日志）'),
    h('div', { style: { ...S.fieldLabel, margin: '16px 0 5px' } }, '本机 CLI 概况'),
    h('div', { style: S.infoBox },
      h('div', {}, `解析到 ${cli.flags?.length || 0} 个 CLI flags · ` +
        `${cli.mapped_flags?.length || 0} 个已映射到设置项 · ` +
        `${cli.mapped_settings_keys?.length || 0} 个 settings.json 键`),
      h('div', {}, `${cli.subcommands?.length || 0} 个子命令 · ` +
        `${cli.slash_commands?.length || 0} 个 slash 命令（见功能矩阵）`),
      h('div', { style: { marginTop: '6px', color: P.faint } },
        'CLI 帮助输出来自本机 claude.exe --help，非文档臆测。')))
}

function CliMatrix() {
  const cli = useValue(cliInfo)
  useValue(themeTick)
  const color = { full: P.green, partial: P.accent2, limited: P.faint }
  const label = { full: '已配置', partial: '部分', limited: '架构受限' }
  return h('div', {},
    h('div', { style: S.setTitle }, 'CLI 功能矩阵与配置映射'),
    h('div', { style: S.setSub },
      '逐项对照本机 Claude Code 2.1.322。「架构受限」是 headless 单轮执行 + 协议桥的固有限制，不是配置缺失。'),
    h('table', { style: S.table },
      h('thead', {}, h('tr', {},
        h('th', { style: S.th }, '能力'),
        h('th', { style: S.th }, '状态'),
        h('th', { style: S.th }, '实现方式 / 限制'))),
      h('tbody', {}, ...(cli.features || []).map((f, i) =>
        h('tr', { key: i },
          h('td', { style: S.td }, f.name),
          h('td', { style: S.td },
            h('span', { style: { ...S.pill, background: (color[f.status] || P.faint) + '22',
                                 color: color[f.status] || P.faint } },
              label[f.status] || f.status)),
          h('td', { style: { ...S.td, color: P.dim } }, f.detail))))),
    h('div', { style: { ...S.fieldLabel, margin: '18px 0 6px' } },
      `已映射 CLI flags（${cli.mapped_flags?.length || 0}）`),
    h('div', { style: S.infoBox },
      (cli.mapped_flags || []).join('  ·  ') || '—'),
    h('div', { style: { ...S.fieldLabel, margin: '14px 0 6px' } },
      `已映射 settings.json 键（${cli.mapped_settings_keys?.length || 0}）`),
    h('div', { style: S.infoBox },
      (cli.mapped_settings_keys || []).join('  ·  ') || '—'),
    h('div', { style: { ...S.fieldLabel, margin: '14px 0 6px' } },
      `本机 CLI 全部 flags（${cli.flags?.length || 0}）`),
    h('div', { style: S.infoBox },
      (cli.flags || []).join('  ·  ') || '—'),
    h('div', { style: { ...S.fieldLabel, margin: '14px 0 6px' } }, 'Slash 命令'),
    h('div', { style: S.infoBox },
      (cli.slash_commands || []).join('  ·  ') || '—'))
}

function SettingsApp() {
  const schema = useValue(settingsSchema)
  const values = useValue(settingsValues)
  const tab = useValue(settingsTab)
  const dirty = useValue(settingsDirty)
  const loaded = useValue(settingsLoaded)
  const cli = useValue(cliInfo)
  const b = useValue(backend)
  useValue(themeTick)

  useEffect(() => {
    if (!ctxRef || loaded) return
    void loadBackend(false)
  }, [])

  if (!schema.length) {
    return h('div', { style: S.setWrap },
      h('div', { style: S.setNav },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '4px 8px 12px' } },
          h(ClaudeMark, { size: 17 }),
          h('span', { style: { fontWeight: 650, fontSize: '0.73rem' } }, 'Claude Code')),
        h('div', { style: { padding: '6px 8px', fontSize: '0.64rem', color: P.faint } },
          '配置尚未载入')),
      h('div', { style: S.setMain },
        h('div', { style: S.setTitle }, '全量设置尚未载入'),
        h('div', { style: { ...S.setSub, lineHeight: 1.75 } },
          b.error || '正在从插件后端读取配置架构（107 项）…'),
        h('button', { style: { ...S.primary, marginTop: '10px' },
                      onClick: () => { backend.set({ ...backend.get(), error: '' }); void loadBackend(false) } },
          '重新读取')))
  }

  const tabs = [...new Set(schema.map((i) => i.group)), TAB_MATRIX, TAB_UPGRADE]
  const activeTab = tabs.includes(tab) ? tab : (tabs[0] || '模型与推理')
  const items = schema.filter((i) => i.group === activeTab)

  return h('div', { style: S.setWrap },
    h('div', { style: S.setNav },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '6px',
                          padding: '4px 8px 12px' } },
        h(ClaudeMark, { size: 17 }),
        h('span', { style: { fontWeight: 650, fontSize: '0.73rem' } }, 'Claude Code')),
      ...tabs.map((t) =>
        h('button', {
          key: t,
          style: { ...S.setNavBtn,
                   background: t === activeTab ? P.bg3 : 'transparent',
                   color: t === activeTab ? P.text : P.dim,
                   fontWeight: t === activeTab ? 650 : 400 },
          onClick: () => settingsTab.set(t)
        }, t)),
      h('div', { style: { marginTop: '14px', padding: '8px', fontSize: '0.62rem',
                          color: P.faint, lineHeight: 1.6, borderTop: `1px solid ${P.line}` } },
        `共 ${schema.length} 项配置`,
        h('div', {}, `${cli.mapped_flags?.length || 0} 个 CLI flags`),
        h('div', {}, `${cli.mapped_settings_keys?.length || 0} 个 settings 键`),
        h('div', { style: { marginTop: '5px' } },
          '设置持久化到插件 .runtime/plugin-settings.json，不修改 ~/.claude/settings.json。'))),
    h('div', { style: S.setMain },
      activeTab === TAB_UPGRADE ? h(UpgradePanel, {})
        : activeTab === TAB_MATRIX ? h(CliMatrix, {})
        : h('div', {},
            h('div', { style: S.setTitle }, activeTab),
            h('div', { style: S.setSub },
              '每项都标注了对应的 CLI flag 或 settings.json 键。保存后由后端生成单会话 settings.json 与完整命令行参数，下一条消息生效。'),
            h('div', { style: S.setActions },
              h('button', { style: S.primary, onClick: () => void saveSettings() },
                dirty ? '保存设置 *' : '保存设置'),
              h('button', { style: S.secondary, onClick: () => void resetSettings() },
                '恢复默认'),
              h('button', { style: S.secondary, onClick: () => void loadBackend(false) },
                '重新读取'),
              h('span', { style: { fontSize: '0.65rem', color: P.faint } },
                dirty ? '有未保存的修改' : '已与后端同步')),
            h('div', { style: S.infoBox },
              h('div', {}, '审批方式：',
                h('b', {}, approvalOn() ? '插件内弹窗（host）' : '关闭（none）'),
                ' · 权限模式：',
                h('b', {}, PERMISSION_LABELS[permMode()] || permMode())),
              h('div', {}, '开启后 CLI 通过 --permission-prompt-tool 把授权请求交给插件；卡片支持 Y 允许 / A 始终允许 / N 拒绝 / Esc 拒绝，超时自动拒绝。'),
              h('div', {}, '快捷键：输入框内 Shift+Tab 或 ⌘/Ctrl+Shift+P 循环权限模式 · ⌘/Ctrl+Shift+B 开关审批 · ⌘/Ctrl+Shift+Y / N / J 允许 / 拒绝 / 始终允许。')),
            items.length
              ? h('div', {}, ...items.map((item) =>
                  h(Field, { key: item.key, item, value: values[item.key] })))
              : h('div', { style: S.note }, '正在读取配置架构…'))))
}

/* ------------------------------------------------------------------ */
/* Plugin manifest                                                      */
/* ------------------------------------------------------------------ */
export default {
  id: PLUGIN_ID,
  name: 'Claude Code Desktop',
  description: '本机 Claude Code 的图形化工作区：全量 CLI 配置、附件、一键升级、插件内工具审批、思考链与全部 Hermes 模型。',

  register(ctx) {
    ctxRef = ctx

    /* Restore persisted sessions when the host provides plugin storage. */
    try {
      const saved = ctx.storage && ctx.storage.get
        ? ctx.storage.get('sessions', null) : null
      if (Array.isArray(saved) && saved.length) {
        sessions.set(saved.map((s) => ({ ...s, traces: s.traces || [],
                                         attachments: [], messages: s.messages || [] })))
        const aid = ctx.storage.get('activeId', null)
        if (aid && getSession(aid)) activeId.set(aid)
      }
    } catch (_) { /* older host without storage */ }

    ctx.register({
      id: 'page', area: ROUTES_AREA, data: { path: '/claude-code' },
      render: () => h(CcApp, {})
    })
    ctx.register({
      id: 'nav', area: SIDEBAR_NAV_AREA, order: 45,
      data: { codicon: 'code', label: 'Claude Code', path: '/claude-code' }
    })
    ctx.register({
      id: 'pane', area: PANES_AREA, title: 'Claude Code',
      data: { placement: 'main' }, render: () => h(CcApp, {})
    })
    ctx.register({
      id: 'chip', area: STATUSBAR_AREAS.right, order: 120,
      render: () => h(CcChip, {})
    })

    const palette = (id, label, keywords, run) => ctx.register({
      id, area: PALETTE_AREA,
      data: { id: 'cc.' + id, label, keywords: ['cc', 'claude', ...keywords], run }
    })
    palette('open', 'Claude Code: 打开工作区', ['code', 'desktop'],
      () => { if (typeof host.navigate === 'function') host.navigate('/claude-code') })
    palette('newSession', 'Claude Code: 新建会话', ['session', 'new'], newSession)
    palette('clearSession', 'Claude Code: 清空当前会话', ['clear', 'reset'],
      () => clearSession(activeId.get()))
    palette('refreshModels', 'Claude Code: 刷新 Hermes 模型目录', ['model', 'refresh'],
      () => void loadBackend(true))
    palette('openSettings', 'Claude Code: 打开全量设置', ['settings', 'config'],
      () => openSettings())
    palette('checkUpgrade', 'Claude Code: 检查更新', ['update', 'upgrade', 'version'],
      () => { openSettings(TAB_UPGRADE); void checkUpgrade() })
    palette('upgrade', 'Claude Code: 一键升级', ['update', 'upgrade', 'install'],
      () => { openSettings(TAB_UPGRADE); void doUpgrade('npm') })
    palette('cliMatrix', 'Claude Code: 查看 CLI 功能矩阵', ['cli', 'features', 'flags'],
      () => openSettings(TAB_MATRIX))
    palette('export', 'Claude Code: 复制当前会话为 Markdown', ['export', 'copy'],
      () => {
        const s = getSession(activeId.get())
        if (!s || !ctx.os || !ctx.os.writeClipboard) return
        const md = '## ' + s.title + '\n\n' + (s.messages || []).map((m) =>
          m.role === 'user' ? '**You:** ' + m.text
            : m.role === 'assistant' ? '**Claude:** ' + m.text
            : '`' + m.role + '` ' + String(m.text || m.hint || '')).join('\n\n')
        void ctx.os.writeClipboard(md)
        status.set('会话已复制到剪贴板')
      })
    palette('revealCwd', 'Claude Code: 在资源管理器中打开工作目录', ['folder', 'cwd'],
      () => {
        const s = getSession(activeId.get())
        const cwd = (s && s.cwd) || backend.get().defaultCwd
        if (cwd && ctx.os && ctx.os.revealPath) void ctx.os.revealPath(cwd)
      })
    palette('toggleThinking', 'Claude Code: 切换思考过程显示', ['thinking', 'trace'],
      () => {
        const c = cfg()
        updateSetting('show_thinking', c.show_thinking === false)
        status.set('思考过程显示：' + (c.show_thinking === false ? '开启' : '关闭'))
      })
    palette('cyclePermission', 'Claude Code: 循环切换权限模式 (Shift+Tab)',
      ['permission', 'mode', 'shift tab'], () => cyclePermissionMode())
    palette('toggleApproval', 'Claude Code: 开关插件内工具审批',
      ['permission', 'approval', 'host', 'none'], () => toggleApprovalMode())
    palette('approveAllow', 'Claude Code: 允许当前审批', ['approval', 'allow', 'yes'],
      () => decideFirst('allow'))
    palette('approveAlways', 'Claude Code: 始终允许当前工具', ['approval', 'always'],
      () => decideFirst('always_allow'))
    palette('approveDeny', 'Claude Code: 拒绝当前审批', ['approval', 'deny', 'no'],
      () => decideFirst('deny'))

    ctx.register({
      id: 'kb-open', area: KEYBINDS_AREA,
      data: { id: 'kb.cc.open', label: 'Claude Code: 打开工作区', category: 'view',
              defaults: ['mod+shift+c'],
              run: () => { if (typeof host.navigate === 'function') host.navigate('/claude-code') } }
    })
    ctx.register({
      id: 'kb-upgrade', area: KEYBINDS_AREA,
      data: { id: 'kb.cc.upgrade', label: 'Claude Code: 一键升级', category: 'view',
              defaults: ['mod+shift+u'], run: () => void doUpgrade('npm') }
    })
    const keybind = (id, label, keys, run) => ctx.register({
      id, area: KEYBINDS_AREA,
      data: { id: 'kb.cc.' + id, label, category: 'claude-code',
              defaults: keys, run }
    })
    keybind('kb-perm-mode', 'Claude Code: 循环切换权限模式（同终端 Shift+Tab）',
      ['mod+shift+p'], () => cyclePermissionMode())
    keybind('kb-approval-toggle', 'Claude Code: 开关插件内工具审批',
      ['mod+shift+b'], () => toggleApprovalMode())
    keybind('kb-approval-allow', 'Claude Code: 允许当前审批 (Y)',
      ['mod+shift+y'], () => decideFirst('allow'))
    keybind('kb-approval-always', 'Claude Code: 始终允许当前工具 (A)',
      ['mod+shift+j'], () => decideFirst('always_allow'))
    keybind('kb-approval-deny', 'Claude Code: 拒绝当前审批 (N)',
      ['mod+shift+n'], () => decideFirst('deny'))

    ctx.registerSettingsPage?.({
      id: 'settings',
      title: 'Claude Code Desktop',
      icon: 'code',
      render: () => h(SettingsApp, {})
    })
  }
}
