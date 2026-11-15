# Configuration

Three kinds of state, in three different places. Knowing which is which saves an hour.

| What | Where | Written by | Survives a reinstall |
| :- | :- | :- | :- |
| Settings the panel shows (107 of them) | `<hermes-home>/desktop-plugins/claude-code-parity/.runtime/plugin-settings.json` | the panel, via `POST /settings` | yes |
| Deployment facts (provider headers, stream-only, system guard) | `<hermes-home>/config.yaml` or the environment | you | yes |
| Relay token, history, uploads | same `.runtime/` directory | the plugin | token yes; history is yours |

---

## Provider request shaping

Some OpenAI-compatible gateways require the client to identify itself, only answer a
streamed request, or mangle a `system` turn. All three are facts about **one deployment**,
not about the protocol, so nothing about them is in the source. You declare them:

```yaml
plugins:
  entries:
    claude-code-parity:
      providers:
        my-gateway:
          headers:
            X-Client: my-app
            X-Request-ID: "{uuid}"
          stream_only: true
          guard_system: true
```

### `headers`

Sent on every request the bridge makes to that provider.

- Values are strings. YAML will otherwise turn `5.9.3` into a float and `true` into a
  boolean, so quote anything that is not obviously a string: `X-IDE-Version: "5.9.3"`,
  `X-Private-Data: "true"`.
- A value of exactly `{uuid}` becomes a fresh `uuid4()` per request. Use it for the
  tracing headers gateways expect (`X-Request-ID`, `X-Conversation-ID`, …).
- These headers are spread **last** when the request is built, so they win over the
  bridge's own `content-type`, `authorization` and `accept`.

### `stream_only`

Forces `stream: true` for that provider.

### `guard_system`

Rewrites the request so the gateway cannot lose your instructions:

- the real system prompt is folded into the first user turn as
  `[System instructions — follow exactly] … [User request] …`
- a short neutral system message takes its place

Use it when tool turns start ignoring the system prompt through a non-Anthropic gateway.

### Defaults

**Both switches default to `true` as soon as a provider has any configured header.** A
gateway that needs identifying headers is by definition non-standard; needing the other two
is the common case, not the exception. Opt out explicitly:

```yaml
          headers: { X-Client: my-app }
          stream_only: false
          guard_system: false
```

### Precedence

First hit wins.

1. `CCP_PROVIDER_HEADERS` — JSON, `{"<slug>": {"X-Client": "my-app"}}`. Also
   `CCP_STREAM_ONLY_PROVIDERS='<slug>,<slug>'`.
2. `plugins.entries.claude-code-parity.providers.<slug>` — as above. Plugin-owned
   namespace: it cannot shadow a built-in provider.
3. `providers.<slug>.extra_headers` — the field Hermes itself uses for a custom provider.
   Read as a fallback so a provider you already configured keeps working, and so the two
   systems agree instead of fighting.

### Verify

```bash
curl -s -H 'x-ccp-token: <token>' http://127.0.0.1:47823/health
```

```json
"provider_shaping": {"my-gateway": {"headers": 14, "stream_only": true, "guard_system": true}}
```

Counts only — no header names, no values. A slug missing from that map means the plugin is
reading a different `config.yaml`: compare the `home` field in the same response with the
file you edited.

If it is missing right after an edit, the gateway has the old config cached. `hermes gateway
restart`.

---

## The settings page

107 entries, six groups, generated from two places: Claude Code's own CLI flags and
`settings.json` keys. Each entry shows the flag or path it drives, so the page doubles as
documentation.

| Group | Representative entries |
| :- | :- |
| Models & reasoning | `default_model`, `effort` (`--effort` / `effortLevel`), `max_effort_level`, `fallback_model`, allow/deny model lists, `force_extended_thinking`, fast mode, cache TTLs, `autocompact`, `max_budget_usd`, `json_schema`, `vision_mode` |
| Permissions & safety | `permission_mode`, `permission_prompts`, `approval_timeout`, `allowed_tools`, `disallowed_tools`, `ask_tools`, `tools`, `add_dir`, bypass switches, `restricted`, `safe_mode`, `bare`, `sandbox`, `auto_mode`, `auto_mode_disabled` |
| Prompt & output | `system_prompt`, `append_system_prompt`, prompt snapshot, `output_style`, `language`, `theme`, `editor_mode`, attribution, `verbose`, `debug`, `prompt_suggestions`, hook events |
| Sessions & extensions | `continue`, `fork_session`, `session_name`, `session_id`, no-persistence, `agents`, `agent`, `mcp_config`, `mcp_strict`, plugin dir/URL, hooks, `env_extra`, IDE, Chrome, retention, memory |
| Runtime | `default_cwd`, `timeout`, `tool_policy` |
| Appearance & UI | `ui_palette`, thinking display, timeline, tool cards, message view, font scale |

### How a setting reaches the CLI

- **Flags** are appended to the turn's `argv`.
- **Paths** are written into a `--settings` file, and only when the value differs from the
  default. Writing all 107 defaults destabilises the CLI in headless mode (an explicit
  `"disableAutoMode": false` triggers an endless `api_retry` before the bridge is ever
  called), and an explicit `false` is semantically the default anyway.
- `env_extra` is merged into the child process environment last, but `ANTHROPIC_*` is
  written by the plugin after it and cannot be overridden — otherwise the CLI would stop
  talking to the bridge.

### Default working directory

Empty means: use Hermes' `terminal.cwd`, then fall back to your home directory. A path that
does not exist fails the turn immediately with `NotADirectoryError: [WinError 267]`, which is
deliberate — silently substituting a different directory would let a turn write somewhere
you did not choose.

---

## Files

```
<hermes-home>/
  config.yaml                                   provider shaping lives here (plugins.entries)
  plugins/claude-code-parity/                   backend half
  desktop-plugins/claude-code-parity/
    plugin.js                                   panel half
    .runtime/
      relay.json                                per-install relay token
      plugin-settings.json                      the 107 settings
      history/{archived,trash}/                 archive and trash
      history/titles.json, flags.json           names and flags you set
      uploads/                                  attachments
  logs/                                         gateway logs
```

`CLAUDE_CONFIG_DIR` (default `~/.claude`) is read for `projects/*.jsonl` — the CLI's own
session storage. It is never written by this plugin.

---

## Environment variables

| Variable | Effect |
| :- | :- |
| `CCP_PROVIDER_HEADERS` | JSON map of per-provider headers, highest precedence |
| `CCP_STREAM_ONLY_PROVIDERS` | comma-separated slugs forced to `stream: true` |
| `CCP_MOBILE_PORT` | phone client port, default `47830` |
| `CLAUDE_CONFIG_DIR` | where the CLI keeps sessions, default `~/.claude` |
| `HERMES_HOME` | read to locate `config.yaml`, `plugins/`, `desktop-plugins/` |

---

## Upgrading the Claude Code CLI

The panel's upgrade path tries, in order, and keeps the previous working binary so a bad
release is one click from being rolled back:

1. `claude update`, then a version re-check
2. `npm install @anthropic-ai/claude-code@latest` in the project that depends on it
3. copy `claude.exe` straight out of the `claude-code-win32-x64` platform package

**Repair install** is the fourth, separate path: no network, no reinstall — it only restores
the missing native binary, which is what you want when the 160-byte npm shim is what got
picked up.
