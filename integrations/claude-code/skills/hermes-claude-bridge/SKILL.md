---
name: hermes-claude-bridge
description: Drive the Claude Code Desktop workspace that this repo ships for Hermes Desktop — handshake with its loopback relay, list the model catalogue, start a turn, poll its event stream, and answer tool approvals. Use when the user asks to run, script, or debug this workspace's backend, or when an agent needs to talk to it from outside the panel.
---

# Talking to the Hermes Claude bridge

The workspace ships two halves that talk over HTTP:

- a **dashboard plugin** (`dashboard/plugin_api.py`) mounted by Hermes at
  `/api/plugins/claude-code-parity`
- a **loopback relay** that serves the same router on `127.0.0.1:47823-47828`,
  so the Desktop panel works even when the dashboard has an auth provider.

Everything below targets the relay. The router paths are identical on the
dashboard mount.

## 1. Get a token

The relay is loopback-only and refuses any `http://` / `https://` `Origin`
(a browser tab cannot reach it; `file://`, `app://` and `null` are allowed).

```bash
curl -s http://127.0.0.1:47823/relay/handshake
```

That prints `{"token":"<43 characters>"}`. Keep the value in a shell variable —
paste it at the prompt rather than baking it into a script:

```bash
read -r TOKEN
```

The token is generated once per installation and persisted at
`<hermes-home>/desktop-plugins/claude-code-parity/.runtime/relay.json`. It is
not a remote credential — it exists so a random web page cannot drive a local
API. Send it as the `x-ccp-token` header on every call.

If the handshake answers 403, the relay is not up (Hermes Desktop is not
running, or the plugin is not enabled). Port 47823 busy? Try 47824-47828.

## 2. Check health

```bash
curl -s -H "x-ccp-token: $TOKEN" http://127.0.0.1:47823/health
```

Read `claude_ok` before anything else: `false` means the CLI binary was not
found or is a 160-byte npm shim, and `claude_problem` says which. Also useful:

- `models` / `groups` — size of the catalogue
- `provider_shaping` — per provider, how many request headers are configured
  and whether stream-only / system-guard are on. Diagnostics only: no values.

## 3. List models

```bash
curl -s -H "x-ccp-token: $TOKEN" 'http://127.0.0.1:47823/models?probe=false'
```

The answer has `models` (a flat list of `{id, provider, model, group, online,
local}`), `groups` (per provider, with its `models` map), `total`, and
`recommended` — the id to use when the user has no preference. Use
`provider` + `model` from a flat entry as the `provider` and `model` in the
next step. `probe=true` (the default) makes a live call per provider to fill
`online`, which is slower.

## 4. Run a turn

```bash
curl -s -X POST http://127.0.0.1:47823/chat \
  -H "x-ccp-token: $TOKEN" -H 'content-type: application/json' \
  -d '{"text":"summarise this repo","provider":"<slug>","model":"<id>","cwd":"<absolute path>","tool_policy":"auto"}'
```

Returns `{"job_id": "..."}` immediately. The turn runs as a real `claude`
process. Fields:

| field | meaning |
| :- | :- |
| `text` | the user turn (required unless `attachments` is non-empty) |
| `provider`, `model` | from `/models` |
| `cwd` | absolute path; must exist, otherwise the job fails with WinError 267 |
| `tool_policy` | `auto` sends tool schemas, `describe` only names them, `off` sends none |
| `attachments` | `[{path, name, kind, mime}]`, local files already on disk |
| `resume_id` | continue that Claude Code session id |
| `fork_session` | with `resume_id`, create a new session id |
| `session_key` | groups related jobs for history; defaults to the job id |
| `timeout` | seconds, default from saved settings |

## 5. Poll events

```bash
curl -s -H "x-ccp-token: $TOKEN" \
  "http://127.0.0.1:47823/poll?job_id=<id>&cursor=0"
```

Pass the returned `cursor` back to get only new events. Every event has a
`kind` field:

| kind | payload |
| :- | :- |
| `init` | `session_id`, `model` |
| `delta` | `text` — assistant text as it arrives |
| `reasoning_delta` | `text` — thinking, if the model emits it |
| `reasoning_done` | `chars`, `tools` |
| `blocks` | `blocks: [{type, text}]` — the finished message |
| `usage` | `input_tokens`, `output_tokens` |
| `result` | `ok`, `text`, `session_id`, `usage` |
| `done` | `error` — the terminal event |

`done: true` on the poll envelope means the process exited; `error` is the
reason when it did not finish cleanly.

## 6. Approvals

When the CLI wants a tool the policy does not allow, the turn blocks and an
entry appears in:

```bash
curl -s -H "x-ccp-token: $TOKEN" http://127.0.0.1:47823/approvals
```

The answer is `{pending: [{id, job_id, tool_name, input, tool_use_id,
created_at, deadline, remaining}], count, mode}`, where `mode` is the saved
approval mode. Answer it — the three actions are the three the panel shows:

```bash
curl -s -X POST http://127.0.0.1:47823/approvals/decide \
  -H "x-ccp-token: $TOKEN" -H 'content-type: application/json' \
  -d '{"id":"<approval id>","action":"allow"}'
```

`allow` = this once, `always_allow` = remember that tool for the session,
`deny` = refuse. `updated_input` (an object) can rewrite the tool arguments,
and `message` (up to 400 chars) is shown to the model as the reason for a
denial. An unanswered approval is auto-denied after `approval_timeout`
seconds so a headless CLI cannot hang forever.

## 7. Language

Every endpoint that returns display text accepts `?lang=en`. Without it the
strings are Chinese. Model output, tool output and anything the user typed are
never translated.

## Ground rules

- Never hardcode the relay token, a provider slug, or a vendor header into
  source. The token is per install; provider headers belong in configuration
  (see `docs/configuration.md`).
- Never send a turn without a `cwd` that exists on this machine.
- One turn = one `claude` process. MCP servers and background bash are rebuilt
  every turn, so do not expect a long-lived MCP connection between turns.
