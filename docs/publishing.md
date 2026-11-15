# Publishing

Two marketplaces, two completely different bars. The Hermes one is a reviewed pull request;
the Claude Code one is a file in this repo.

---

## Hermes Agent

### Today: installable by URL

No listing is needed for this to work — `hermes plugins install` accepts a Git URL or
`owner/repo`:

```bash
hermes plugins install MnemosyneOS/claude-code-parity --enable
hermes gateway restart
```

The plugin declares no `update_url`, so nothing updates itself: install from the repo and
Hermes records the source, and `hermes plugins check-updates` / `hermes plugins update
claude-code-parity` follow it when you ask them to.

### For the curated catalog: a PR to the Hermes repository

The catalog is a directory of YAML files in the `hermes-agent` repository
(`plugin-catalog/<name>.yaml`). Presence is the trust signal, so it is gated by a human
review. The rules that matter for this plugin, from that directory's `README.md`:

1. **Human-merged.** Entries are added only by PR to `hermes-agent`, reviewed and merged by
   a maintainer. No self-serve registry.
2. **Exact SHA pins.** The entry pins a full 40-character commit SHA. Branches, tags and
   short SHAs are rejected. Installs clone and check out exactly that commit.
3. **No self-updating code.** A listed plugin must not fetch and replace *its own files*.
4. **SHA bumps are new PRs**, re-reviewed as an upstream commit range.
5. **Owner or major contributor submits**; drive-by submissions of third-party repos are
   declined.
6. **Declared capabilities must match reality** at the pinned commit.
7. **The install scanner runs at admission** — `hermes plugins validate`'s `security scan`:
   `dangerous` fails, `caution` is shown to the reviewer.
8. **Desktop plugins stay inside the SDK surface** — no prototype patching, no
   `eval`/`new Function`, no foreign `import()`, no script-tag injection, no reaching into
   the app's markup or internal stores.
9. **No runtime overrides of Hermes core** — no rebinding core functions, methods, module
   attributes or private dicts. Undocumented core imports are a warning for the reviewer.
10. **Dependency policy is the plugin's own.**

### Entry template

Fill this in with the SHA of the release you are submitting:

```yaml
name: claude-code-parity
repo: https://github.com/MnemosyneOS/claude-code-parity
subdir: ""                       # the plugin is the repository root
sha: "<40-character commit sha>"
title: Claude Code Desktop
description: >-
  A graphical, non-terminal Claude Code workspace inside Hermes Desktop. Drives the
  real claude CLI as a child process, so every flag and settings.json key still
  works. 107 generated settings, tool approvals in the panel or from a phone on the
  same Wi-Fi, attachments, a live thinking/tool chain, session history with archive
  and trash, one-click CLI upgrade with rollback, and every model Hermes already
  has. English and Chinese UI.
maintainer: MnemosyneOS
tier: community
category: desktop
requires_hermes: ">=0.21.0"
docs_url: https://github.com/MnemosyneOS/claude-code-parity#readme
version: "2.2.0"
platforms: [windows, macos, linux]
capabilities:
  provides_tools: []
  provides_hooks: []
  provides_middleware: []
  requires_env: []
```

`category` and `platforms` follow whatever the surrounding entries use — copy from a
neighbour rather than inventing a value.

### What the reviewer will ask

Answer these before the PR, not during it.

**"Does rule 3 apply? It has a check-for-updates button."**
No, and the distinction is the whole point: the updater upgrades the **Claude Code CLI**
(`claude update`, or `npm install @anthropic-ai/claude-code@latest`, or copying the binary
out of the platform package). It never touches this plugin's own files — it does not fetch
a `plugin.js`, does not download a release, does not rewrite itself. The plugin's own
updates reach users through a SHA-bump PR, exactly as the rule intends.

**"`hermes plugins validate` prints two warnings."**
Yes, both are `⚠`, not `✗`:

- `no __init__.py — capability probe skipped (manifest-only plugin)`. The agent half is a
  dashboard plugin (`dashboard/manifest.json` + `dashboard/plugin_api.py`), which does not
  register tools or hooks, so there is nothing to probe. `capabilities` is empty on purpose.
- `private core imports` — `hermes_cli.providers.resolve_provider_full`,
  `hermes_cli.inventory.load_picker_context`, `hermes_cli.inventory.build_model_options_payload`,
  `hermes_cli.auth.resolve_api_key_provider_credentials`,
  `tui_gateway.launch_profile_policy.owner_secret_scope`. These are **reads**: the plugin
  asks Hermes which providers and models exist, and which profile's secret scope a request
  belongs to. Nothing is rebound or assigned, which is why `no core override` passes. If an
  official seam exists for "list the authenticated providers and their model catalogue", this
  plugin will switch to it — that is a desirable follow-up, not a blocker.

**"It spawns processes."**
One `claude` process per turn, because that is how the CLI works non-interactively
(`--output-format stream-json`). It is not a daemon and does not survive the turn.

**"Where do request headers and vendor names live?"**
Nowhere in the source. Provider headers, stream-only and system-guard are per-provider
configuration read at runtime (`docs/configuration.md`). The source contains no vendor name,
no credential and no personal path, which is also why `security scan` reports `safe`.

### The gate

```bash
hermes plugins validate .
```

Must end with `Validation passed.` on the exact commit you pin. Run it on a clean checkout,
not a working tree with untracked files.

---

## Claude Code

Different marketplace, different model: `.claude-plugin/marketplace.json` in this repository
*is* the registry entry. Anyone can add it immediately:

```bash
claude plugin marketplace add MnemosyneOS/claude-code-parity
claude plugin install claude-code-parity@mnemosyneos
```

Relevant rules from the plugin reference:

- `.claude-plugin/marketplace.json` must have `name`, `owner`, and a `plugins` array.
- Each `plugins[]` entry needs at least `name` and `source`. Here `source` is
  `./integrations/claude-code` — a subdirectory, so the Claude Code payload does not have to
  share a root with the Hermes plugin.
- A plugin's own `.claude-plugin/plugin.json` is optional but recommended. Every component
  path in it must start with `./` and must exist inside the plugin root.
- Components are discovered from `skills/`, `commands/`, `agents/`, `hooks/hooks.json`,
  `.mcp.json`. Skills are the recommended unit; `commands/` is flat markdown.

That is why this repo ships `integrations/claude-code/skills/hermes-claude-bridge/` — the
bridge contract as a skill — rather than a stub manifest with no content.

**Naming:** the entry name and the manifest name must agree (`claude-code-parity`), or
component namespacing and `enabledPlugins` disagree. Keep them identical.

---

## Release checklist

1. Bump `version` in **four** places, which must agree:
   `plugin.yaml`, `dashboard/manifest.json`, `integrations/claude-code/.claude-plugin/plugin.json`,
   `.claude-plugin/marketplace.json`.
2. `hermes plugins validate .` → `Validation passed.`
3. `node --check desktop/plugin.js` and a syntax check on the Python.
4. Reinstall over a working copy and restart, then prove the two things that break silently:
   - `GET /health` → `claude_ok: true`, a version string, and `provider_shaping` showing what
     you configured
   - one real turn through `POST /chat` → a `result` event with text
5. Scan for deployment facts that belong in configuration, not source:

   ```bash
   grep -riE 'C:\\\\Users|/home/[a-z]|192\.168\.|10\.[0-9]+\.|bearer [A-Za-z0-9]{20,}' \
     dashboard/ desktop/
   ```

   Expect no hits. This will not catch a vendor name you invented — read the diff for that.
6. Both READMEs updated if the surface changed.
7. `CHANGELOG.md` entry.
8. Tag, push, and for the catalog: open the SHA-bump PR with the notes above.
