"""Claude Code permission-prompt MCP server (stdio, stdlib only).

Claude Code 2.1.x supports a hidden CLI flag::

    --permission-prompts host --permission-prompt-tool mcp__cc_approval__approve

When a tool call needs approval in a headless `-p` run, the CLI calls that MCP
tool with ``{tool_name, input, tool_use_id}`` and expects a single text block
whose text is a JSON permission result::

    {"behavior": "allow", "updatedInput": {...}}
    {"behavior": "deny",  "message": "..."}

This server is spawned by the CLI for one turn. It cannot talk to the Hermes
dashboard directly (different process, no shared auth), so it uses a tiny
file-based IPC channel in ``CC_APPROVAL_DIR``:

    req-<id>.json  <- server writes the pending prompt
    dec-<id>.json  <- dashboard writes the user's decision

Files are written atomically (.tmp + os.replace) so a polling reader never
sees a half-written JSON document. If nobody answers within
``CC_APPROVAL_TIMEOUT`` seconds the request is denied automatically, so a
headless CLI can never hang forever waiting for a person.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path

DIR = Path(os.environ.get("CC_APPROVAL_DIR") or "").resolve()
TIMEOUT = max(5.0, float(os.environ.get("CC_APPROVAL_TIMEOUT") or "120"))
SERVER_NAME = "cc_approval"
TOOL_NAME = "approve"


def _send(msg: dict) -> None:
    sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _answer(tool_name: str, original_input: dict, tool_use_id: str) -> dict:
    """Block until the Hermes dashboard writes a decision file."""
    if not DIR.is_dir():
        return {"behavior": "deny", "message": "审批通道未初始化（缺少目录），已自动拒绝"}
    rid = uuid.uuid4().hex[:16]
    deadline = time.time() + TIMEOUT
    try:
        _atomic(DIR / f"req-{rid}.json", {
            "id": rid, "tool_name": tool_name, "input": original_input,
            "tool_use_id": tool_use_id, "created_at": time.time(),
            "deadline": deadline, "timeout": TIMEOUT,
        })
    except Exception as exc:
        return {"behavior": "deny", "message": f"审批请求写入失败：{exc}"}

    dec = DIR / f"dec-{rid}.json"
    while time.time() < deadline:
        if dec.is_file():
            try:
                data = json.loads(dec.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.1)
                continue
            action = str(data.get("action") or "deny")
            if action in ("allow", "always_allow"):
                out = {"behavior": "allow"}
                changed = data.get("updated_input")
                if isinstance(changed, dict) and changed:
                    out["updatedInput"] = changed
                return out
            return {"behavior": "deny",
                    "message": str(data.get("message") or "用户在 Hermes Desktop 中拒绝了此操作")}
        time.sleep(0.2)
    return {"behavior": "deny", "message": f"审批超时（{int(TIMEOUT)} 秒无人响应），已自动拒绝"}


def _handle(req: dict) -> dict | None:
    method = req.get("method")
    rid = req.get("id")
    if method == "server/discover":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "initialize":
        pv = (req.get("params") or {}).get("protocolVersion") or "2025-11-25"
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": pv,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": "2.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [{
            "name": TOOL_NAME,
            "description": "Answer a Claude Code tool permission prompt from Hermes Desktop",
            "inputSchema": {
                "type": "object", "additionalProperties": True,
                "properties": {
                    "tool_name": {"type": "string"},
                    "input": {"type": "object"},
                    "tool_use_id": {"type": "string"},
                    "permission_suggestions": {"type": "array"},
                    "blocked_path": {"type": "string"},
                    "decision_reason": {"type": "string"},
                }},
        }]}}
    if method == "tools/call":
        params = req.get("params") or {}
        args = params.get("arguments") or {}
        result = _answer(str(args.get("tool_name") or "unknown"),
                         args.get("input") if isinstance(args.get("input"), dict) else {},
                         str(args.get("tool_use_id") or ""))
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
    if method in ("resources/list", "prompts/list"):
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "resources" if method == "resources/list" else "prompts": []}}
    if rid is None:
        return None  # notification (e.g. notifications/initialized)
    return {"jsonrpc": "2.0", "id": rid, "result": {}}


def main() -> None:
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception:
            continue
        try:
            resp = _handle(req)
            if resp is not None:
                _send(resp)
        except Exception:
            # Never let an exception kill the stdio loop: CLI would hang.
            try:
                _send({"jsonrpc": "2.0", "id": req.get("id"),
                       "error": {"code": -32603, "message": traceback.format_exc()[-400:]}})
            except Exception:
                pass


if __name__ == "__main__":
    main()
