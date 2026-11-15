# Claude Code Desktop

A graphical Claude Code workspace that lives inside **Hermes Desktop** — no terminal, no
`settings.json` editing, no lost sessions. It drives the real `claude` CLI as a child
process, so every flag and every `settings.json` key still works, and it routes the CLI at
whatever model you already have configured in Hermes, local or remote.

**English** · [简体中文](README.zh-CN.md)

- 107 settings generated from the CLI's own flags and `settings.json` keys
- Tool approvals inside the panel — or from your phone on the same Wi-Fi
- Attachments, a live thinking/tool chain, session history with archive and trash
- Every model Hermes already has, in the composer's model picker
- One-click CLI upgrade, with backup and rollback
- English and Chinese UI, switchable in the sidebar

---

## Contents

- [Why not just the terminal?](#why-not-just-the-terminal)
- [How it works](#how-it-works)
- [What you need](#what-you-need)
- [Install, from zero](#install-from-zero)
- [The one thing you may have to configure](#the-one-thing-you-may-have-to-configure)
- [Using it](#using-it)
- [Tool approvals](#tool-approvals)
- [Phone access](#phone-access)
- [Language](#language)
- [Installing into Claude Code itself](#installing-into-claude-code-itself)
- [Security model](#security-model)
- [Troubleshooting](#troubleshooting)
- [Repository layout](#repository-layout)
- [Development](#development)
- [License and trademarks](#license-and-trademarks)

---

## Why not just the terminal?

The CLI is excellent and this plugin does not reimplement it. What it adds is the part a
terminal cannot give you:

| | Terminal | This plugin |
| :- | :- | :- |
| Every CLI flag | type them each time | one schema-driven settings page, remembered |
| `settings.json` keys | hand-edit JSON | generated from the official key names, injected with `--settings` |
| Tool approvals | `y` / `a` / `n` at the prompt | a card in the panel, or on your phone |
| Thinking and tool calls | interleaved text | a timeline you can collapse |
| Sessions | `--resume` and memory | a list with rename, archive, restore, permanent delete |
| Attachments | paste a path | drag and drop, becomes an `@path` the CLI can read |
| Switching models | env vars and restarts | a picker in the composer |
| Upgrading | npm and luck | button, with a backup and a rollback path |

## How it works

```
┌──────────────────────────────┐
│ Hermes Desktop               │
│  ┌────────────────────────┐  │
│  │ Claude Code panel      │  │   desktop/plugin.js
│  │ (React, in the host)   │  │
│  └───────────┬────────────┘  │
│              │ HTTP          │
│  ┌───────────▼────────────┐  │
│  │ dashboard/plugin_api.py│  │   the Hermes plugin backend
│  └───────────┬────────────┘  │
└──────────────┼───────────────┘
               │ spawns one process per turn
      ┌────────▼─────────┐
      │ claude CLI       │   --output-format stream-json --settings <runtime file>
      └────────┬─────────┘
               │ ANTHROPIC_BASE_URL=http://127.0.0.1:<bridge>
      ┌────────▼─────────┐
      │ loopback bridge  │   Anthropic wire format  ⇄  OpenAI wire format
      └────────┬─────────┘
               │
      ┌────────▼─────────┐
      │ your Hermes model│   whatever you authenticated: Anthropic, OpenAI-compatible,
      └──────────────────┘   a local Qwen on :8080, a gateway, anything
```

Three consequences worth knowing:

1. **No Anthropic account is required.** The CLI is pointed at the bridge with
   `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_MODEL`, so it never calls
   Anthropic unless your chosen model is an Anthropic one.
2. **One turn is one process.** MCP servers and background bash are rebuilt every turn.
   That is a cost, and it is why long-lived MCP connections are not reproduced here.
3. **The bridge speaks both wire formats.** The CLI talks Anthropic; almost every other
   provider talks OpenAI. The bridge converts per turn, including tool calls.

## What you need

| | |
| :- | :- |
| OS | Windows 10 1809+, macOS 13+, or Linux (glibc) |
| Hermes Agent | **0.21 or newer**, with Hermes Desktop |
| Claude Code CLI | any recent version — the binary only, no login needed |
| A model | at least one already configured in Hermes |
| Network | internet for the install; none after that unless your model is remote |

## Install, from zero

Five steps, roughly ten minutes. Skip nothing — step 1 is the one people skip.

### Step 1 — Install the Claude Code CLI

This plugin **does not** ship the Claude Code binary. It finds yours and runs it, so
install it first. Pick one method.

**Windows, native installer (recommended, no Node needed):**

```powershell
irm https://claude.ai/install.ps1 | iex
```

**Windows, npm (Node.js 22 or newer; never use `sudo`):**

```powershell
npm install -g @anthropic-ai/claude-code@latest
```

**Windows, WinGet:**

```powershell
winget install Anthropic.ClaudeCode
```

**macOS / Linux / WSL, native installer:**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**macOS / Linux / WSL, npm:**

```bash
npm install -g @anthropic-ai/claude-code@latest
```

**macOS, Homebrew:**

```bash
brew install --cask claude-code
```

Those one-liners that pipe a download into a shell are Anthropic's and Nous Research's own
published installers, quoted verbatim from their docs — read them before you run them, as
you should with any installer. Every method above is upstream-official; none is a wrapper
this project wrote.

Verify — open a **new** terminal so `PATH` is refreshed:

```bash
claude --version
```

You should see something like `2.1.325 (Claude Code)`. If the command is not found, the
install directory is not on `PATH`; re-open the terminal, or find the binary and note its
path — you can point the plugin at it in Settings → Upgrade & diagnostics.

> **You do not need to log in.** Running `claude` on its own will offer a login and an
> Anthropic subscription. Skip it: this plugin sets its own base URL and token. If you are
> on Windows and want to double-check that the binary is really installed (and not a
> 160-byte npm shim), look for
> `…/node_modules/@anthropic-ai/claude-code/bin/claude.exe`.

### Step 2 — Install Hermes Agent

**Windows (native, PowerShell):**

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

**Linux / macOS / WSL:**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

**Or** download the packaged desktop app for your platform from the Hermes site and skip
straight to step 3 — the bundle already contains the agent.

Check it:

```bash
hermes --version
```

This plugin declares `requires_hermes: ">=0.21.0"`; an older release will refuse it.

### Step 3 — Give Hermes a model

The panel lists whatever Hermes can reach, so configure at least one:

```bash
hermes model
```

Or add an OpenAI-compatible endpoint to `config.yaml` by hand:

```yaml
providers:
  local-qwen:
    name: Local Qwen
    base_url: http://127.0.0.1:8080/v1
    api_key: local
    api_mode: chat_completions
    default_model: Qwen3.8-Flash-Next-EXL3-4.05bpw
```

### Step 4 — Install this plugin

```bash
hermes plugins install MnemosyneOS/claude-code-parity --enable
```

`--enable` skips the confirmation prompt. Then restart the gateway so the Python backend
is mounted — a user plugin's `dashboard/plugin_api.py` only loads when the plugin is both
enabled and the gateway has restarted:

```bash
hermes gateway restart
```

Verify both halves landed:

```bash
hermes plugins list
```

You should see `claude-code-parity` as `enabled`. On disk that is
`<hermes-home>/plugins/claude-code-parity/` (backend) and
`<hermes-home>/desktop-plugins/claude-code-parity/` (panel).

### Step 5 — Open the panel

Launch Hermes Desktop and pick **Claude Code Desktop** in the sidebar. The first screen
is a health readout; if the CLI was found you are done. Type something.

If the panel says the backend is not connected, see
[Troubleshooting](#troubleshooting) — it is almost always a gateway restart or the plugin
not being in `plugins.enabled`.

## The one thing you may have to configure

**Request headers, and two behavioural switches, are configuration — not code.**

Nothing vendor-specific is hardcoded anywhere in this repository. If your provider needs
a client to identify itself with extra headers (some gateways do), says *"Illegal API
invocation"* or HTTP 400 until it sees them, or mishandles a plain `system` turn, you
declare that per provider:

```yaml
plugins:
  entries:
    claude-code-parity:
      providers:
        <your-provider-slug>:
          headers:                    # sent on every bridged request
            X-Client: my-app
            X-Request-ID: "{uuid}"    # each {uuid} is expanded per request
          stream_only: true           # force stream:true
          guard_system: true          # fold the system prompt into the first user turn
```

All three keys are optional:

- `headers` — sent on every request to that provider. `{uuid}` becomes a fresh UUID each
  call, which is what gateways use for tracing.
- `stream_only` — some gateways only answer when `stream` is true.
- `guard_system` — some gateways drop or mis-handle the `system` message, and tool turns
  then lose the instructions. This rewrites the system prompt into the first user turn and
  installs a short neutral system message instead.

**Both switches default to `true` as soon as a provider has any configured header**, on the
assumption that identifying headers exist precisely because the gateway is non-standard.
Set either to an explicit `false` to opt out.

Three ways to supply it, first hit wins:

1. Environment — good for CI, Docker, and machines you do not want to edit:

   ```bash
   CCP_PROVIDER_HEADERS='{"my-gateway": {"X-Client": "my-app"}}'
   CCP_STREAM_ONLY_PROVIDERS='my-gateway,other-gateway'
   ```

2. `plugins.entries.claude-code-parity.providers.<slug>` in `config.yaml`, as above.
   This namespace belongs to the plugin and cannot shadow a built-in provider.

3. `providers.<slug>.extra_headers` in `config.yaml` — the field Hermes itself uses for a
   custom provider. Read as a fallback so a provider you already configured keeps working.

**Check that it took effect** without reading any values:

```bash
curl -s -H 'x-ccp-token: <token>' http://127.0.0.1:47823/health
```

```json
"provider_shaping": {"my-gateway": {"headers": 14, "stream_only": true, "guard_system": true}}
```

Counts only: how many headers were found, and whether the two switches ended up on. If a
provider you configured is missing from that map, the plugin is reading a different
`config.yaml` than you edited — see `home` in the same response.

## Using it

**The composer** is the whole interaction: type, drag in files, pick a model from the
bottom-right, send. The panel also registers actions in Hermes' own command palette — open
the workspace, new session, clear the current session, refresh the model catalogue, open
the full settings page, check for an upgrade, apply it, view the CLI feature matrix, export
the session as Markdown.

**The CLI feature matrix** (Settings → Upgrade & diagnostics) is an honest ledger of what a
non-interactive, one-process-per-turn workspace can reproduce and what it cannot. Slash
commands are listed there for reference; commands that need a live TUI — modal dialogs,
`Esc Esc` rewind, a split-pane diff — are marked as not reproduced, with the workaround. Use
`--resume` into a past session instead of rewinding.

**The settings page** has 107 entries in six groups, each mapped to the flag or
`settings.json` path it drives:

| Group | Covers |
| :- | :- |
| Models & reasoning | default model, effort and its ceiling, fallback model, allow/deny lists, thinking, fast mode, cache TTLs, auto-compaction, budget cap, structured output |
| Permissions & safety | permission mode, approval mode and timeout, allowed/blocked/ask tools, built-in tool set, extra directories, bypass switches, restricted and safe mode, sandbox, autoMode |
| Prompt & output | system prompt replace/append, snapshot, output style, language, theme, editor mode, attribution, verbose and debug, hook events |
| Sessions & extensions | continue, fork, session name and id, persistence, subagents, MCP config, plugin dirs and URLs, hooks, env vars, IDE and Chrome integration, retention, memory |
| Runtime | default working directory, per-turn timeout, tool-call policy |
| Appearance & UI | palette (Claude coral, Claude dark, or follow Hermes), thinking display, timeline, tool cards, message view, font scale |

Settings live in `<hermes-home>/desktop-plugins/claude-code-parity/.runtime/plugin-settings.json`
and are injected into every turn with `--settings`. **Your own `~/.claude/settings.json` is
never rewritten** — the settings page shows its path read-only so you can compare.

**History** lists every session with its project, model and turn count. Rename, archive,
restore from trash, or delete permanently. A burst of deletes is throttled on purpose: more
than a few within four seconds pauses with a message, so a stuck key cannot wipe the list.

**Upgrade** re-runs the installer for you (`claude update`, then npm, then a direct copy
from the platform package), verifies the new binary, and keeps the previous working version
so a broken release can be rolled back with one click.

## Tool approvals

The CLI is given `--permission-prompt-tool`, an MCP server this plugin ships
(`dashboard/approval_mcp.py`). When a tool needs a decision the CLI blocks, the panel shows
a card with the tool name and its arguments, and you answer:

| Action | Meaning |
| :- | :- |
| **Allow** | this once |
| **Always allow** | for the rest of the session, for that tool |
| **Deny** | refuse; the model sees the refusal and adapts |

Set **Approval mode** to `host` to get these cards. With `none` nothing is ever asked and
any tool that needs approval is denied outright — that is the headless-safe setting. There
is a timeout (default in Settings → Permissions & safety): if nobody answers, the request is
auto-denied so a headless CLI can never hang forever.

The same three actions exist on the phone, so you can approve a long-running job from the
next room instead of walking back to the computer.

## Phone access

The panel serves a second, phone-sized client on your LAN, on its own port, with its own
passphrase:

1. In the panel, open **Phone access**. It lists every LAN address plus a QR code.
2. Phone and computer must be on the **same Wi-Fi**. Scan the code, or type the URL.

Notes that save time:

- The **passphrase is fixed** per installation; only the **IP changes** when your router
  hands out a new lease after a reboot. Re-scan, do not reconfigure.
- Phone endpoints are a strict allow-list, not the whole API: list, send, poll, approve.
- The phone page is a single static file with no build step, and it is bilingual too.

## Language

The sidebar has an **EN / 中文** switch. It is not a partial skin:

- The panel's own strings are translated in one place — every string literal the UI renders
  goes through a single translator inside the JSX factory, so a new button cannot silently
  ship monolingual.
- The **backend's** strings are translated server-side. The settings schema, the capability
  matrix, the upgrade log and every diagnostic are authored in Chinese and sent in English
  when the UI asks for `?lang=en`; the panel now appends that parameter to every call.
- The phone client has its own table and picks the language from `?lang=`, then
  `localStorage`, then `navigator.language`.
- **Your content is never translated.** Model output, tool output and anything you typed
  pass through untouched; only the plugin's own chrome changes.

## Installing into Claude Code itself

This repository is also a Claude Code marketplace, so `claude` can add it:

```bash
claude plugin marketplace add MnemosyneOS/claude-code-parity
claude plugin install claude-code-parity@mnemosyneos
```

What you get there is the **bridge skill** (`integrations/claude-code/skills/`): the exact
HTTP contract for the running workspace — how to handshake with the loopback relay, list
models, start a turn, poll its event stream, and answer approvals — so Claude Code (or any
agent) can drive this backend from outside the panel.

What you do **not** get is the desktop panel: that half is a Hermes Desktop plugin and only
runs inside Hermes. The two halves are the same project and the same version number; the
Hermes half is the product, the Claude Code half is the integration surface.

For the Hermes side, `hermes plugins install` takes a Git URL or `owner/repo` directly, so
no marketplace step is needed. Listing it in the curated Hermes catalog is a pull request to
the upstream catalog; `hermes plugins validate` is the gate it has to pass, and this tree
passes it.

## Security model

Read this before exposing the panel to anything.

- **The loopback relay token is generated per installation**, persisted in
  `.runtime/relay.json`, and never committed. A token in the source tree would be public and
  therefore useless; the point is that a random web page you happen to visit cannot drive a
  local API.
- **The relay only answers loopback** (`127.0.0.1`, `::1`) and **refuses any `http://` or
  `https://` `Origin`** — `file://`, `app://` and `null` are allowed, which is what the
  Desktop window sends. A page in a browser tab cannot reach the handshake.
- **CORS is a regex allow-list**, not `*`.
- **The phone client has its own passphrase and its own port**, separate from the panel, and
  only the endpoints it needs.
- **No telemetry, no analytics, no phone-home.** The only network traffic is to the model
  endpoint you configured, plus whatever the CLI itself does for its own update check.
- **Approvals map to the CLI's own permission system.** This plugin does not weaken Claude
  Code's permissions; it gives you a better place to answer them. `bypassPermissions` is
  available because the CLI has it, and it is off.

## Troubleshooting

| Symptom | Cause | Fix |
| :- | :- | :- |
| Panel says the backend is not connected | the Python backend only mounts when the plugin is enabled **and** the gateway restarted | `hermes plugins enable claude-code-parity` then `hermes gateway restart` |
| `claude_ok: false`, "file is only 160 bytes" | you pointed it at the npm shim (`claude.cmd`) instead of the binary | Settings → Upgrade & diagnostics → **Repair install**; the plugin prefers `node_modules/@anthropic-ai/claude-code/bin/claude.exe` |
| `… 403 {"detail":"relay token required"}` | stale token after an upgrade regenerated it | reload the panel; it re-handshakes automatically on 403 |
| Handshake answers 403 | the relay is not up, or the request came from a web origin | start Hermes Desktop; do not call it from a browser tab |
| Upstream `HTTP 400 code:11128 Illegal API …` | your gateway wants identifying headers | [configure provider headers](#the-one-thing-you-may-have-to-configure) |
| `NotADirectoryError: [WinError 267]` on send | the working directory does not exist | Settings → Runtime → default working directory, or clear it to fall back to Hermes' `terminal.cwd` then your home |
| `[claude-code:unrecognized_model]` on stderr | the CLI does not know that model name; harmless, the bridge replaces the request | ignore, or pick the model through the composer so the bridge maps it |
| Phone cannot connect | different Wi-Fi, VPN on, or the IP changed | same network, VPN off, re-scan the code |
| Everything works but answers are slow | `probe=true` in the model picker, or a model that is slow to first token | the picker caches; check the provider's own latency |

Where the logs are: `<hermes-home>/logs/`. The panel's own diagnostics are in
Settings → Upgrade & diagnostics, and `GET /health` (with the relay token) is the same data
as JSON.

## Repository layout

```
plugin.yaml                     Hermes plugin manifest (agent half)
dashboard/
  manifest.json                 panel registration
  plugin_api.py                 backend: settings schema, jobs, bridge, relay, phone
  mobile_page.py                the phone client (single static file, bilingual)
  approval_mcp.py               MCP server that answers CLI permission prompts
desktop/
  plugin.js                     the panel (React, no build step)
integrations/claude-code/
  .claude-plugin/plugin.json    Claude Code plugin manifest
  skills/hermes-claude-bridge/  the bridge contract, as a Claude Code skill
.claude-plugin/marketplace.json Claude Code marketplace entry
docs/                           configuration, architecture, mobile, publishing
```

## Development

There is no build step for the panel: `desktop/plugin.js` is loaded as-is. The backend is
plain Python run by Hermes' own interpreter.

```bash
# the admission gate — must print "Validation passed."
hermes plugins validate .

# reinstall over your working copy after an edit
hermes plugins install MnemosyneOS/claude-code-parity --force --enable
hermes gateway restart
```

Two rules this codebase keeps, and a reviewer should hold it to:

1. **No credentials, vendor names or personal paths in source.** Deployment facts live in
   configuration; the source reads them.
2. **One i18n choke point per half.** The panel translates inside its JSX factory, the
   backend inside its response builder. Do not sprinkle translations at call sites.

## License and trademarks

MIT — see [LICENSE](LICENSE).

Claude and Claude Code are trademarks of Anthropic, PBC. This project is an independent
interface to the Claude Code CLI and is not affiliated with, endorsed by, or sponsored by
Anthropic. Hermes and Hermes Agent are products of Nous Research; this plugin is a
third-party plugin for that host. The full notice is in [NOTICE](NOTICE).
