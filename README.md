# the-team

A portable home for a personal OpenCode agent fleet running on a single homelab
server (Kubernetes + systemd).

## Repository layout

`fleet/` is the live OpenCode global config directory itself: when the service
launch environment sets `OPENCODE_CONFIG_DIR` to the absolute `fleet/` path,
OpenCode loads `fleet/opencode.jsonc`, `fleet/AGENTS.md`, `fleet/agents/`, and
`fleet/skills/` directly with no installer, generator, or second config.

```text
fleet/              # OpenCode global config root (OPENCODE_CONFIG_DIR)
├── agents/         # Custom Markdown agent definitions
├── skills/         # Shared skills, each with a SKILL.md
├── AGENTS.md       # Shared fleet-wide instructions
└── opencode.jsonc  # Tracked global OpenCode config
examples/           # Example snippets (fake values only)
docs/               # Workflow documentation (docs/ship.md)
scripts/ship/       # Check runner and ship workflow scripts
tests/              # Ship workflow tests
```

Private runtime siblings (`service.json`, `cli.json`, `auth.json`, `*.env`,
`*.log`) live on disk under `fleet/` when active and are ignored by `.gitignore`
(deny-by-default under `fleet/`). Never commit or print `service.json` or auth
files.

## Native setup

Clone this repository at a stable, writable absolute path and supply the
host-specific placeholders in the OpenCode background service's launch
environment (systemd drop-in `Environment=` lines or a `0600` `EnvironmentFile`
outside the repository):

```text
OPENCODE_CONFIG_DIR=/home/<login>/Projects/the-team/fleet
FLEET_HOME=/home/<login>
FLEET_OPENROUTER_MCP_URL=https://<private-mcp-host>/<private-path>
FLEET_UVX_PATH=/absolute/path/to/uvx
```

Host-specific values appear in `fleet/opencode.jsonc` only as native
`{env:...}` placeholders (`{env:FLEET_HOME}`, `{env:FLEET_OPENROUTER_MCP_URL}`,
`{env:FLEET_UVX_PATH}`). No secrets or private host paths are stored in Git.

After setting or changing launch environment variables, restart the OpenCode
service and verify with:

```sh
opencode debug paths config
opencode debug agents
```

Normal edits to `fleet/opencode.jsonc`, `fleet/AGENTS.md`, `fleet/agents/`, and
`fleet/skills/` are watched and reloaded by OpenCode automatically (start a new
session after editing instructions). When running CLI write commands like
`opencode mcp add ... --global`, set `OPENCODE_CONFIG_DIR` to `fleet/` so they
do not write to `~/.config/opencode/`. Never leave a competing
`fleet/opencode.json` beside `fleet/opencode.jsonc`.

## Fleet agents

The fleet mixes low-cost models for chat and read-only research with stronger
models for coding, UI craft, CAD, and audits — avoiding multi-hop
planner-to-cheap-coder handoffs.

| Agent | Mode | Model | Role |
| --- | --- | --- | --- |
| **Cal** (`cal`, default) | Primary | `openrouter/muse-ember-200k#medium` | Everyday chat, brainstorming, memory, web search, and read-only repo/k8s/systemd checks |
| **Build** (`build`, built-in) | Primary | `openrouter/gemini-4-neon-200k#high` | Hands-on coding, debugging, homelab ops, and shipping in one context |
| **Frontend** (`frontend`) | Primary / Subagent | `openrouter/kimi-k3.1-pro-270k#high` | UI design, implementation, and review with zero UI slop |
| **Mark** (`mark`) | Primary | `openrouter/sol-256k#high` | Mechanical/CAD lead (`cad` skill, Blender/FreeCAD workflows, geometric checks) |
| **Reviewer** (`reviewer`) | Primary / Subagent | `openrouter/claude-opus-5.5-270k#high` | Read-only code, PR, plan, infra, and CAD (`cad-review`) audits |
| **Explore** (`explore`, built-in) | Subagent | `openrouter/muse-ember-200k#high` | Low-cost codebase search and web/doc lookups (pinned so it never inherits an expensive caller model) |
| **General** (`general`, built-in) | Subagent | *(inherits caller)* | General-purpose subagent for independent parallel multi-step work |

Built-in `plan` and `chat` remain disabled. Custom agent models and permissions
live in each agent's `fleet/agents/<name>.md`; built-in agent overrides live in
`fleet/opencode.jsonc`.

### Permissions philosophy

This is a single-user homelab environment, not a multi-tenant enterprise
sandbox:

- OpenCode's default base policy allows reading, `external_directory` (so
  `@references` and `/tmp/opencode` work cleanly), and prompts on `*.env`
  reads.
- Read-only agents (`cal`, `reviewer`) deny edits, mutating shell commands, and
  mutating MCP tools while allowing normal read-only `git` (`status`, `diff`,
  `log`, `show`, `branch`, `rev-parse`), read-only GitHub and Kubernetes
  inspection, and `@references`.
- Implementers (`build`, `frontend`, `mark`, `general`) have full edit, shell,
  and tool access and confirm with the user before destructive or
  live-impacting homelab actions.

### Model context caps

Custom aliases in `fleet/opencode.jsonc` cap working context to prevent runaway
sessions and stay below provider long-context pricing cliffs (`muse-ember-200k`
at 195k input / 200k context below Meta's 200k 3× tier; `gemini-4-neon-200k` at
200k / 32k output so sessions compact early instead of growing across Neon's 1M
window; `sol-256k` below OpenAI's 272k 2× tier; `kimi-k3.1-pro-270k` and
`claude-opus-5.5-270k` at 270k / 32k output). Automatic compaction stays
enabled. Selecting an agent does not override a model already saved on an
existing session.

## Local checks

Enable the repository pre-commit hook once per checkout:

```sh
git config --local core.hooksPath .githooks
```

Run checks directly with:

```sh
./scripts/ship/check
```

This runs `shellcheck`, `bash -n`, Python syntax checks, the ship unit tests
(`tests/`), JSON/JSONC validation, agent/skill frontmatter checks, private-path
leak checks on `fleet/opencode.jsonc`, and `.gitignore` allowlist checks.

## Ship workflow

The opt-in ship workflow (`fleet/skills/ship/SKILL.md` and `scripts/ship/`) is
documented in [docs/ship.md](docs/ship.md).

## Adding content

- **Agents:** Add `fleet/agents/<name>.md` with OpenCode V2 frontmatter.
- **Skills:** Add `fleet/skills/<skill-id>/SKILL.md` (add an explicit
  `.gitignore` exception for any supporting files alongside `SKILL.md`).
- **Shared instructions:** Edit `fleet/AGENTS.md`.
- **Global config:** Edit `fleet/opencode.jsonc` using `{env:...}` placeholders
  for host-specific paths or URLs.

See the [OpenCode V2 documentation](https://opencode.ai/docs/) for supported
configuration fields and formats.
