# Changelog

All notable changes to this project. Versions follow the Hermes plugin manifest in
`plugin.yaml`, which is the single number the host reads.

## 2.2.0 — first public release

The first version published outside the machine it was built on. Everything below describes
what that release contains and what had to change to make it publishable.

### Removed before publishing

- **Every credential and vendor name in source.** Provider request headers used to be built
  by a vendor-named function with a hardcoded token; the relay token was a literal in both
  the panel and the backend. Both are gone: headers are configuration (see below) and the
  relay token is generated per installation and persisted.
- **Every personal path.** The CLI is located by search, not by a hardcoded install path;
  the default working directory is your home directory, not the author's project tree; the
  settings help text no longer names a machine.
- **The vendor-specific branch in the model resolver.** It now keys off configured facts
  instead of a provider name prefix.

### Security

- Relay token is per-install (`secrets.token_urlsafe(24)`, persisted to `.runtime/relay.json`)
  and handed out over `GET /relay/handshake`, which is loopback-only and **refuses any
  `http://` / `https://` `Origin`**. A committed token would have been public and therefore
  worthless.
- CORS on the relay narrowed from `allow_origins=["*"]` to a regex allow-list
  (`file://`, `app://`, `null`).
- The panel re-handshakes automatically on a 403, so a regenerated token is not a broken
  panel.

### Added

- **Provider request shaping as configuration**, three layered sources, first hit wins:
  `CCP_PROVIDER_HEADERS` env → `plugins.entries.claude-code-parity.providers.<slug>` →
  `providers.<slug>.extra_headers`. Supports `headers` (with `{uuid}` expanded per request),
  `stream_only` and `guard_system`, the last two defaulting to true once a provider has any
  header.
- `GET /health` now reports `provider_shaping` — per provider, a header **count** and the two
  switches. The answer to "did my config get picked up?" without reading any value.
- **Backend i18n.** 232 display strings (settings schema, capability matrix, upgrade log,
  diagnostics) are translated server-side on `?lang=en`, exact match plus a fragment table for
  strings concatenated with live values. The panel appends `lang` to every API call from one
  place.
- **Phone client is bilingual**, with `?lang=` → `localStorage` → `navigator.language`.
- `integrations/claude-code/` — a real Claude Code plugin payload (the bridge contract as a
  skill) and a marketplace entry, so `claude plugin marketplace add` has something to install.
- `docs/`: architecture, configuration, phone access, publishing.

### Fixed

- **The npm shim was being mistaken for the binary.** `_find_claude()` matched `claude.cmd`
  in `PATH` (160 bytes), so every turn failed with "installation damaged". It now prefers
  `node_modules/@anthropic-ai/claude-code/bin/claude.exe` and never returns a `.cmd` or
  `.ps1`.
- The panel's `lang` parameter is no longer lost on relay calls, which carry their own
  query string.
- Settings help text for the working directory says what actually happens: Hermes'
  `terminal.cwd`, then your home directory.

### Known limits

- One process per turn, so MCP servers and background bash are rebuilt every turn. Long-lived
  MCP connections are not reproduced; the feature matrix says so in the UI.
- TUI-only interactions (modal dialogs, `Esc Esc` rewind, split-pane diffs) are not
  reproduced. `--resume` is the workaround for rewinding.
- `hermes plugins validate` reports two warnings, not failures: no `__init__.py` (this is a
  manifest-only dashboard plugin) and seven reads of undocumented `hermes_cli` modules. Both
  are explained in `docs/publishing.md` for a catalog reviewer.
