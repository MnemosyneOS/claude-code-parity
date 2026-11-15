# Architecture

How the two halves fit together, and why each piece exists.

## Components

| Component | File | Runs in | Job |
| :- | :- | :- | :- |
| Panel | `desktop/plugin.js` | Hermes Desktop renderer | UI, state, event rendering, i18n |
| Backend | `dashboard/plugin_api.py` | Hermes gateway process (Python) | settings schema, job control, bridge, relay, history, phone |
| Approval MCP | `dashboard/approval_mcp.py` | a child process of `claude` | answers the CLI's permission prompts |
| Phone page | `dashboard/mobile_page.py` | served as static HTML | the same workspace, phone-sized |
| Relay | inside `plugin_api.py` | a thread in the gateway | serves the same router on loopback |
| Mobile server | inside `plugin_api.py` | a thread in the gateway | serves the phone page + a small API on the LAN |

## Ports

| Port | What | Bind | Auth |
| :- | :- | :- | :- |
| dashboard | Hermes' own | Hermes decides | cookie or native grant |
| 47823–47828 | loopback relay | `127.0.0.1` only | `x-ccp-token`, loopback, no web origin |
| 47830 | phone client | `0.0.0.0` (LAN) | `?t=` passphrase |
| OS-assigned (ephemeral) | the bridge, per turn | `127.0.0.1` only | `ANTHROPIC_AUTH_TOKEN` set by the plugin |

The relay tries 47823 first and walks up when a port is taken. `GET /relay` reports which
one it got. Override the phone port with `CCP_MOBILE_PORT`.

## One turn, end to end

```
panel                 backend                    claude CLI              bridge            provider
  │  POST /chat         │                            │                      │                  │
  ├────────────────────►│ validate, resolve model,   │                      │                  │
  │                     │ write --settings file      │                      │                  │
  │  {job_id}           │                            │                      │                  │
  │◄────────────────────┤ spawn ────────────────────►│                      │                  │
  │  GET /poll?cursor=0 │                            │  OpenAI-shaped req   │                  │
  │◄────────────────────┤◄── stream-json events ─────┤─────────────────────►│  OpenAI req      │
  │                     │                            │                      ├─────────────────►│
  │  events: init,      │                            │                      │  SSE             │
  │  reasoning_delta,   │                            │◄─────────────────────┤◄─────────────────┤
  │  delta, blocks,     │                            │  (bridge converts    │                  │
  │  usage, result      │                            │   per turn)          │                  │
  │  done               │                            │                      │                  │
```

The bridge is started per turn and listens on loopback. It exists because the CLI speaks
the Anthropic Messages API and nearly every other provider speaks OpenAI chat completions.
It converts in both directions, including tool calls and tool results, and it injects the
provider's configured headers (see [configuration](configuration.md)).

## Settings: generated, not hand-written

`SCHEMA` in `plugin_api.py` is a list of 107 entries, each with:

- `key` — the plugin's own name for it
- `group` / `label` / `help` — what the UI shows
- `type` — `text`, `select`, `switch`, `json`, `number`, `tags`…
- `flag` — the CLI flag it maps to, if any
- `path` — the `settings.json` path it maps to, if any
- `default`

Two output channels:

1. **Flags** are appended to `argv` for the turn.
2. **Paths** are written into a `--settings` file. Only values that differ from the default
   are written: dumping all defaults makes the CLI enter an `api_retry` loop before it ever
   calls the bridge (verified against 2.1.322), and an explicit `false` is identical to the
   default anyway.

Your own `~/.claude/settings.json` is never modified. `--settings` points at
`.runtime/plugin-settings.json`.

## Event kinds

Each event the CLI streams becomes a normalized event. The panel renders by `kind`:

| kind | why |
| :- | :- |
| `init` | session id and the model actually in use |
| `thinking_delta`, `reasoning_delta` | thinking text; two kinds because the CLI and an OpenAI upstream report it differently |
| `reasoning_done` | closes the thinking block with a character and tool count |
| `delta` | assistant text |
| `tool_call` | a tool invocation with its input |
| `blocks` | the finished message as structured blocks |
| `usage` | token accounting |
| `permission_request` / `permission_resolved` | an approval opened or closed |
| `log` | plugin-side notices (upgrade progress, environment problems) |
| `result` | the turn's final answer |
| `done` | terminal; `error` is set when the process failed |

The palette is small on purpose: the panel should never have to guess what a provider meant.

## Approvals

```
claude CLI ──stdio(MCP)──► approval_mcp.py ──HTTP──► backend
                                    │                 │
                          writes a decision file      ├── pushes permission_request
                          the CLI is waiting on       │   into the job's event stream
                                                      └── panel or phone answers
                                                          POST /approvals/decide
```

`--permission-prompt-tool` names an MCP tool. The CLI calls it and blocks. The MCP server
turns that into a pending approval with a deadline, pushes it into the job's event stream,
and polls for a decision file. Answering writes `dec-<id>.json`; the MCP server returns the
decision to the CLI.

Three actions: `allow`, `always_allow` (that tool, this session), `deny`. On timeout the
decision is `deny` — a headless process must never hang forever. `updated_input` lets the
panel rewrite the tool arguments before the tool runs, which is how "allow, but with this
path instead" works.

## History

The CLI already writes every session to
`CLAUDE_CONFIG_DIR/projects/<slugified-cwd>/<sessionId>.jsonl`, one JSON object per line.
There is no listing or pruning outside the interactive `/resume` picker, so the backend
reads those files directly to list, reopen (`--resume <id>`), rename, archive and delete.

Archive and trash move files into `.runtime/history/{archived,trash}/`; permanent delete
removes them for good. Titles the user sets live in `.runtime/history/titles.json`, flags in
`flags.json`. Deleting in bulk is throttled: more than a handful within four seconds pauses
and warns, so a stuck key cannot wipe the list.

## i18n

Two choke points, one per half:

- **Panel** — the JSX factory `h()` translates string children and the display-only props
  `title`, `placeholder`, `aria-label`. Whole-string dictionary first, then a pattern table
  for strings the caller built by concatenation, longest pattern first, iterated until it
  settles. A new button cannot ship monolingual by accident.
- **Backend** — every endpoint that returns display text translates its payload on the way
  out, using `?lang=` on the request. Exact-match table plus a fragment table for strings
  that are concatenated with live values (`"File is only " + "160" + " bytes — corrupted"`).
  Anything without CJK is returned untouched, which is why model output, tool output and
  user input are never rewritten.

The panel appends `lang` to every API call from one place (`withLang` in `api()`).

## Why a relay at all

The gateway authenticates `/api/plugins/<id>/*` with a dashboard session cookie, or a
native grant on a request the Desktop itself signed. When the dashboard has an auth provider
configured, the Desktop window's plugin REST arrives with neither and gets 401 — the panel
shows "backend not connected" while the same routes answer fine from a browser. The relay
serves the same router on loopback under a token, so the panel works in any auth mode. The
official `ctx.rest` door is still tried first; the relay is the fallback, and the panel
reports which channel it is on.
