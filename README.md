# the-team

A portable home for a personal OpenCode agent fleet. The `fleet/agents/`
directory contains reusable agent definitions; `fleet/skills/` contains shared
workflows, including modular CAD modeling and verification.

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

## Local checks and manual deployment

Install the repository-local hooks once per checkout:

```sh
./scripts/install-hooks
```

The check command requires Bash, Python 3, and ShellCheck. The pre-commit hook
runs `scripts/check`, which validates Python syntax, shell syntax and
ShellCheck diagnostics, and the repository's JSON/JSONC configuration. Run it
directly with `./scripts/check` when needed. This repository intentionally has
no test suite, so it has no pre-push test hook.

Deployments are manual only; no Git hook deploys or installs the fleet. To
update the OpenCode assets in the user's config directory, explicitly run:

```sh
./scripts/deploy.sh
```

That command invokes the existing `fleet-install` helper and may alter
OpenCode user configuration. The local hook installer configures Git to use
`.githooks`; the retained pre-commit hook runs checks only.

## Starter agents

The fleet defines six agents under `fleet/agents/`:

| Agent | Model | Context / response budget | Role |
| --- | --- | --- | --- |
| **Cal** (`cal`) | GPT-6 Luna | 270k / 32k | Conversational companion and coordinator |
| **Planner** (`planner`) | GPT-6.1 Sol | 270k / 32k | Read-only investigation and concise task plans |
| **Research** (`research`) | GPT-6 Luna | 270k / 32k | Read-only, evidence-driven web and repository research |
| **Frontend** (`frontend`) | Kimi K3, high reasoning | 270k / 32k | Read-only frontend planning and review; no code edits |
| **CAD** (`cad`) | GPT-6.1 Sol | 270k / 32k | Read-only mechanical-model planning and geometry review |
| **Worker** (`worker`) | GPT-6 Luna | 270k / 32k | Implementation, operations, and verification |

Planner, Research, Frontend, CAD, and Worker can be selected as primary agents or
used as subagents. Cal can delegate evidence-driven web or repository research to
Research, broader investigation and planning to Planner, frontend planning and
review to Frontend, mechanical-model planning and review to CAD, and
implementation to Worker. A persistent workflow
controller is not included yet; Cal's instructions require it to be clear about
that limitation. Cal's delegation permissions and Planner's permissions are in
`fleet/opencode.jsonc`; Research's and CAD's tool permissions are in their agent
definitions. Merge the configuration fragment into each device's OpenCode config
as described below. Select `cal` from OpenCode's agent picker to use the
companion.

### CAD workflow

Cal clarifies design intent, CAD defines feature boundaries and geometric
acceptance criteria, Worker implements and generates evidence, and CAD reviews
the result. CAD and Worker must load the `cad` skill for CAD work. The skill
emphasizes one authoritative master, independently removable feature modules,
and source-level changes rather than code or geometry layered over obsolete
results. Explicit feature flags or clearly commented-out feature calls are
acceptable; compensating repair chains are not.

CAD cannot edit files or use live application tools. Its non-Git shell
diagnostics require approval and must be existing, inspected, non-mutating
commands; it cannot use arbitrary inline Python as a read-only shortcut. If no
safe diagnostic exists, Worker supplies the needed artifacts and CAD reports
the review limitation. Approval gating is not a filesystem sandbox. CAD's
review does not replace Worker's checks or establish physical qualification.
Keep hardware details and revision-specific decisions in each project's own
`AGENTS.md`.

### Fleet models and context budgets

Every fleet agent explicitly selects a shared OpenRouter alias defined in
`fleet/opencode.jsonc`; none inherits an arbitrary caller model by default:

| Local alias | Upstream OpenRouter model | Agents |
| --- | --- | --- |
| `openrouter/luna-270k` | `openai/gpt-6-luna` | Cal, Research, Worker |
| `openrouter/sol-270k` | `openai/gpt-6.1-sol` | Planner, CAD |
| `openrouter/kimi-k3-270k#high` | `moonshotai/kimi-k3` with high reasoning | Frontend |

Research's explicit Luna default matches the usual Cal-led delegation instead
of inheriting a potentially different or unbounded model. Frontend retains Kimi
K3 and its existing high-reasoning selection; it is not upgraded to K3.1 Pro.
The models stay versioned rather than following moving Latest aliases. Shared
definitions keep limits, capabilities, reasoning variants, and pricing estimates
in one place for each model instead of duplicating a definition per agent.

Each alias has a 270,000-token context/input budget and a 32,000-token response
ceiling. The fleet fragment explicitly enables automatic compaction; keep it
enabled when relying on these budgets. The response allowance is within the
context window, not an extra 32k on top. Actual input headroom is smaller because
OpenCode reserves space for output and compaction.

The catalog and OpenRouter model metadata checked on 2026-10-26 place Sol's and
Luna's higher context-pricing tier at 272,000 prompt tokens. Kimi K3 advertises
no context-based tier in the current metadata; its 270k cap is a consistent
working budget, not a claim about a pricing threshold. Pricing estimates are
snapshots and may differ by provider route or change over time.

These budgets guide compaction, not a provider-enforced request-size or spending
cap: token estimates, large tool results, compaction requests, and local
compaction overrides can affect actual billed usage. Verify real usage rather
than assuming a guaranteed price tier.

Merge all three provider alias entries and the compaction setting into each
device's live config before using the updated agent definitions. Installing
Markdown/symlinks alone does not define the aliases. The former CAD-only
`cad-sol-270k` alias has been replaced by shared `sol-270k` in this repository;
an already-installed device needs the new alias as well as the updated agent.
No live device configuration or credentials are changed by editing this fragment.

A model already selected for an existing primary session takes precedence over
the agent default. Select the corresponding fleet alias in that session's model
picker if necessary. Explicit per-run model overrides can also bypass the fleet
budgets. No API credentials or live device configuration belong in this repository.

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
