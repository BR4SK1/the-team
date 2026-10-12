# the-team

A portable home for a personal OpenCode agent fleet. The `fleet/agents/`
directory contains reusable agent definitions; skills and commands can be added
as the team grows.

## Repository layout

```text
fleet/
├── agents/       # Markdown agent definitions
├── skills/       # Skill folders, each with a SKILL.md
├── commands/     # Markdown slash commands
├── AGENTS.md     # Shared fleet-wide instructions
└── opencode.jsonc # Shared OpenCode configuration fragment
profiles/         # Shared configuration fragments by device role
examples/         # Examples for local, uncommitted device settings
scripts/          # Installation helper
```

## Install

Requirements: Python 3 and OpenCode. Clone this repository at a stable path on
each device, then run:

```sh
python3 scripts/fleet-install
```

The installer links the repository's agents, skills, and commands into the
OpenCode user config directory (`$XDG_CONFIG_HOME/opencode`, or
`~/.config/opencode`). It adds the shared instructions to the global
`AGENTS.md` between managed markers, preserving text outside that block. If an
existing global asset conflicts with a fleet name, installation stops rather
than replacing it. Re-run the installer after adding or renaming definitions.

To install into another OpenCode config directory:

```sh
python3 scripts/fleet-install --config-dir /path/to/opencode-config
```

Agent and skill files are symlinks, so pulling a new repository revision updates
them immediately. Open a new OpenCode session after changing instructions.

## Starter agents

The initial fleet defines five agents under `fleet/agents/`:

| Agent | Model | Role |
| --- | --- | --- |
| **Cal** (`cal`) | Luna | Conversational companion and coordinator |
| **Planner** (`planner`) | Sol | Read-only investigation and concise task plans |
| **Research** (`research`) | Inherited | Read-only, evidence-driven web and repository research |
| **Frontend** (`frontend`) | Kimi K3 | Read-only frontend planning and review; no code edits |
| **Worker** (`worker`) | Luna | Implementation, operations, and verification |

Planner, Research, Frontend, and Worker can be selected as primary agents or
used as subagents. Cal can delegate evidence-driven web or repository research to
Research, broader investigation and planning to Planner, frontend planning and
review to Frontend, and implementation to Worker. A persistent workflow
controller is not included yet; Cal's instructions require it to be clear about
that limitation. Cal's delegation permissions and Planner's permissions are in
`fleet/opencode.jsonc`; Research's read-only tool permissions are in its agent
definition. Merge the configuration fragment into each device's OpenCode config
as described below. Select `cal` from OpenCode's agent picker to use the
companion.

## Configuration and device-specific settings

`fleet/opencode.jsonc` and files under `profiles/` are configuration fragments,
not standalone OpenCode config files. Review and merge the settings you want
into that device's `opencode.jsonc` (normally
`$XDG_CONFIG_HOME/opencode/opencode.jsonc`). The installer deliberately does
not rewrite that file, so it cannot erase existing provider, permission, or MCP
settings.

Keep shared, non-secret settings in this repository. Store machine-specific
values and secrets outside the repository. For MCP credentials, use environment
variable references such as `{env:MY_MCP_API_KEY}` in OpenCode configuration;
authenticate OAuth MCPs separately on each device. See
[`examples/device-settings.example.json`](examples/device-settings.example.json)
for a local-settings pattern. Do not commit real credentials or private device
configuration.

## Update and uninstall

Update with `git pull`, then rerun the installer to link newly added files. To
uninstall, remove the symlinks the installer created from the OpenCode config
directory and remove only the marked the-team block from its global `AGENTS.md`.
The installer does not remove files on its own.

## Add content

- Add agents as `.md` files under `fleet/agents/` with OpenCode agent
  frontmatter.
- Add skills as `fleet/skills/<skill-id>/SKILL.md`; put supporting references
  and scripts alongside it.
- Add slash commands as `.md` files under `fleet/commands/`.
- Put reusable team conventions in `fleet/AGENTS.md`.
- Add configuration fragments to `fleet/opencode.jsonc` or a profile in
  `profiles/`.

See the [OpenCode V2 documentation](https://opencode.ai/v2/docs/) for supported
configuration fields and formats.
