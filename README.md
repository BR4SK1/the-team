# the-team

A portable home for a personal OpenCode agent fleet. The `fleet/agents/`
directory contains reusable agent definitions; `fleet/skills/` contains shared
workflows, including modular CAD modeling and verification.

## Repository layout

`fleet/` is not a template to copy or link from. It is the OpenCode
global config directory itself: when the service launch environment sets
`OPENCODE_CONFIG_DIR` to the absolute `fleet/` path, OpenCode loads
`fleet/opencode.jsonc` as its global config and discovers
`fleet/AGENTS.md`, `fleet/agents/`, and `fleet/skills/` directly from
there, with no installer, generator, or second config.

```text
fleet/              # OpenCode global config root (OPENCODE_CONFIG_DIR)
├── agents/         # Markdown agent definitions
├── skills/         # Skill folders, each with a SKILL.md
├── AGENTS.md       # Shared fleet-wide instructions (global file)
└── opencode.jsonc  # Complete tracked global OpenCode config (only config)
examples/           # Device-settings example only (fake values)
scripts/ship/       # Check runner, ship doctor, ship-build, ship-deploy
```

Private runtime siblings (see below) also live on disk under `fleet/`
but are ignored by Git and must never be committed.

## Native setup (no installer)

Requirements: OpenCode V2 and Python 3 / Bash / ShellCheck for checks.
`OPENCODE_CONFIG_DIR` is verified in isolated OpenCode v2.2.6 CLI
read/write tests, in the tagged v2.2.6 source (the global paths layer
overrides its config directory from this variable, and the instruction
plugin resolves `AGENTS.md` as `<config>/AGENTS.md`), and in an
isolated fake-root discovery check (fleet agents, commands, and
skills from the fake config root appear after location
boot and a session; an immediate one-shot query before activation can
show only built-ins). It is not documented in the V2 docs. Recheck it
on upgrade: `opencode debug paths config` in the service environment
must print the absolute `fleet/` path, and `opencode debug agents`
must list the fleet agents. Do not paste a full `opencode debug
config` dump to verify this: it prints the expanded config with
private values; if a config-source check is needed, inspect only the
redacted `type`/`path` fields, never the full output.

Clone this repository once per device at a stable, writable absolute
path (the service environment contains that absolute path, so moving
the checkout breaks it; it must stay writable because the service
writes private siblings such as `service.json` and `cli.json` under
`fleet/`). There is no install, link, generate, or copy step.

### Service launch environment (exact example)

Set these in the environment that launches the OpenCode background
service — not only in an interactive shell or a web frontend. The
example below uses syntactic placeholders (`<login>`); replace them
with the device's real values in the service environment only, never
in Git:

```text
OPENCODE_CONFIG_DIR=/home/<login>/Projects/the-team/fleet
FLEET_HOME=/home/<login>
FLEET_LOGIN_USER=<login>
FLEET_OPENROUTER_MCP_URL=https://<private-mcp-host>/<private-path>
FLEET_UVX_PATH=/absolute/path/to/uvx
```

For a systemd user service, the equivalent launch-environment form is
a drop-in for that service unit:

```ini
[Service]
Environment=OPENCODE_CONFIG_DIR=/home/<login>/Projects/the-team/fleet
Environment=FLEET_HOME=/home/<login>
Environment=FLEET_LOGIN_USER=<login>
Environment=FLEET_OPENROUTER_MCP_URL=https://<private-mcp-host>/<private-path>
Environment=FLEET_UVX_PATH=/absolute/path/to/uvx
```

The same values may instead live in a private environment file
referenced by the unit, which keeps real values out of Git while
remaining part of the launch environment:

```ini
[Service]
EnvironmentFile=/home/<login>/Projects/the-team/fleet.env
```

The private file holds the same five `NAME=value` lines as the
example above, must be owned by the service user with mode `0600`
(or stricter), and must stay outside the repository so it is never
committed. An `EnvironmentFile` is still launch environment, not
service config: the values are supplied to the backend process at
start via the unit. There is no second bootstrap — the fleet
environment is documented only as the service launch environment
(`Environment=` lines or a private `EnvironmentFile`), and the set
above is what the backend (background service) process must see at
start.

Private environment names and formats (all four are required, none
may be blank — an unset or blank value expands to an empty string and
breaks the paths, permission rule, and remote URL that use it):

| Name | Format |
| --- | --- |
| `FLEET_HOME` | Absolute home directory, no trailing slash (for example `/home/<login>`) |
| `FLEET_LOGIN_USER` | Login username: letters, digits, `.`, `_`, `-` only |
| `FLEET_OPENROUTER_MCP_URL` | `https` URL with no userinfo, query, or fragment |
| `FLEET_UVX_PATH` | Absolute path to the `uvx` executable |

These are the only host-specific values in `fleet/opencode.jsonc`;
they appear there solely as native `{env:FLEET_HOME}`,
`{env:FLEET_LOGIN_USER}`, `{env:FLEET_OPENROUTER_MCP_URL}`, and
`{env:FLEET_UVX_PATH}` placeholders. No private value is materialized
in the tracked file.

### Default path, competing file, and native CLI writes

Without `OPENCODE_CONFIG_DIR`, the global config is
`$XDG_CONFIG_HOME/opencode/opencode.json(c)`, or
`~/.config/opencode/opencode.json(c)` when `XDG_CONFIG_HOME` is unset.
With it set to `fleet/`, `fleet/opencode.jsonc` is that global file.

Native CLI file-writing needs its own matching environment: a command
such as `opencode mcp add <name> --global --url <url>` writes to the
global root of the CLI process that runs it, so run it with the same
`OPENCODE_CONFIG_DIR` as the service (for example
`OPENCODE_CONFIG_DIR=/home/<login>/Projects/the-team/fleet opencode mcp add ... --global`).
Without it, `--global` writes to the default `~/.config/opencode/`
location and does not change the fleet service. Omitting `--global`
stays project-only and never touches the fleet global config.

If a native write creates `fleet/opencode.json` (without `c`) next to
the tracked `fleet/opencode.jsonc`, the two compete as the global
config file. Remove the competing `.json` private sibling (it is
ignored by Git) and confirm the loaded source with a redacted
`opencode debug config` field check (inspect only the `type`/`path`
fields, never the full expanded output) before relying on either
file. Never commit a competing `.json`.

### Private runtime siblings and Git review

`service.json`, `cli.json`, auth files, logs, and similar runtime
files live on disk under `fleet/` when it is the config root, but
`.gitignore` denies everything under `fleet/` by default and allows
only `opencode.jsonc`, `AGENTS.md`, `agents/*.md`,
`skills/*/SKILL.md`, and `skills/ship/resources/PR_TEMPLATE.md`.
Do not stage, print, or read the contents
of `service.json`/auth files; inspect only their names via Git
status. Because `fleet/` is both the checkout and the live config
root, review the native Git diff and status before every commit and
run `./scripts/ship/check`; only intended fleet files should appear.

`fleet/opencode.jsonc` is the global OpenCode config (models,
permissions, MCP servers, references, and the rest). It is distinct
from `fleet/service.json`, the background service's private config in
the same directory, which may contain a password and lifecycle
settings (hostname, port, CORS, remote, disabled) and is managed
with `opencode service set` / `get` / `unset`, never edited by hand
as fleet policy. It does not hold the fleet launch environment,
which lives only in the service launch environment (above).
`cli.json` in the same directory holds terminal/TUI preferences only.
The service registration file under the state directory is a separate
discovery record; do not delete or edit service files or the database
while troubleshooting.

### Adoption and reload are separate from committing

Committing this repository does not adopt anything: it does not set
the service launch environment, restart the service, or change a
running backend. Backend adoption — setting the launch environment
above, starting/restarting the service so the new environment takes
effect, and verifying with `opencode debug paths config` (which must
print the absolute `fleet/` path), `opencode debug agents` (which
must list the fleet agents), and MCP status — using only redacted
field checks for any config-source confirmation, never a full
`opencode debug config` dump — is a separate, explicit step after the
checkout is in place.

While a service already using `fleet/` as its config root is running,
the V2 watchers observe the discovered files and trigger a reload
when they are saved: `AGENTS.md` is watched as a file with a short
debounce followed by instruction-discovery reload, and agents,
commands, and skills are watched as `{agents,command,commands,skill,
skills}` definition directories under each config entry and reloaded
on change (emitting `agent.updated` / `command.updated` /
`skill.updated` / `config.updated`). Discovery itself is verified in
the isolated check above (fleet agents and skills appear
after location boot and a session; an immediate one-shot query
before activation can show only built-ins). Hot reload of MCP
servers and live verification of every definition type on save were
not exercised here, so treat a save as a reload trigger, not a
guarantee that every change is already live. In any case, start a
new session after changing instructions. Do not promise hot reload
for launch-environment or config-root changes: changing
`OPENCODE_CONFIG_DIR` or any `FLEET_*` value requires the service to
be started/restarted with the new environment. Pulling a new checkout
revision updates the fleet files in place on the checkout filesystem;
backend adoption (above) is still separate.

## Local checks

Wire the repository-local hooks once per checkout (scoped
verification entry; the commit hook remains the active gate):

```sh
git config --local core.hooksPath .githooks
```

The check command requires Bash, Python 3, and ShellCheck. The active
`.githooks/pre-commit` hook delegates to `scripts/ship/check`, which
validates Python syntax, shell syntax and
ShellCheck diagnostics, the repository's JSON/JSONC configuration, the
complete fleet config shape (including native `{env:...}` placeholders
and the fleet ignore allowlist), and the ship test suite. Run it
directly with `./scripts/ship/check` when needed. The test suite
covers the ship doctor (`tests/ship_doctor_test.py`) and the
ship-build / ship-deploy Git fixtures
(`tests/ship_workflow_test.py`); the fleet itself has no pre-push test
hook.

Shared instructions also define repository/workspace closeout expectations:
do task work in the authorized workspace (never a Git worktree or separate
scratch workspace), keep necessary temporary files in the repository when
feasible, and clean task-created temporary artifacts before PR creation. A PR
normally requires a Git-clean repository with only intended changes committed;
report a valid exception before proceeding. Preserve unrelated or unique user
data, and report Git status separately from workspace cleanup. These rules do
not authorize blanket cleanup or production deployment.

Deployments are manual only; no Git hook deploys or installs the fleet.
There is no deploy script for the fleet: updating the fleet means
pulling the checkout and, separately, ensuring the service launch
environment above is set and the service is started/restarted with it
(backend adoption, above). The scoped hook entry above configures Git
to use `.githooks`; the retained pre-commit hook runs checks only via
`scripts/ship/check`.

## Ship workflow

The one strict opt-in ship standard, the read-only
`scripts/ship/ship-doctor` diagnostic (versioned JSON; exit `0` local
pass, `1` blocked, `2` indeterminate), the fleet skill
`fleet/skills/ship/SKILL.md`, and the workflow scripts
(`scripts/ship/ship-build`, `scripts/ship/ship-deploy`) are documented
in [docs/ship.md](docs/ship.md). Run the doctor only against an
explicit repository path; it inspects bounded allowlisted local
metadata and never writes, executes target code, or uses the network.
The ship skill is loaded explicitly by ID `ship` (for example `@ship`
with no arguments), which loads the fixed Cal-owned workflow.

## Starter agents

The fleet defines seven agents under `fleet/agents/`:

| Agent | Model | Context / response budget | Role |
| --- | --- | --- | --- |
| **Cal** (`cal`) | GPT-6.2 Sol (`sol-256k`), medium reasoning | 256k / 100k output cap | Conversational companion and coordinator |
| **Planner** (`planner`) | GPT-6.2 Sol (`sol-256k`), high reasoning | 256k / 100k output cap | Read-only investigation and concise task plans |
| **Research** (`research`) | Meta Muse Ember (`muse-ember-270k`), max reasoning | 270k / 32k | Read-only, evidence-driven web and repository research |
| **Frontend** (`frontend`) | Kimi K3, high reasoning | 270k / 32k | Read-only frontend planning and review; no code edits |
| **Mark** (`mark`) | GPT-6.2 Sol (`sol-256k`), high reasoning | 256k / 100k output cap | Primary mechanical-design lead; authorized CAD-source and supporting-file edits, builds, and verification |
| **Reviewer** (`reviewer`) | Claude Opus 5.5, high reasoning | 270k / 32k | Review-only primary; evidence-backed review of plans and work, CAD via the `cad-review` skill |
| **Worker** (`worker`) | Meta Muse Ember (`muse-ember-270k`), max reasoning | 270k / 32k | Implementation, operations, and verification |

Cal, Mark, and Reviewer are primary-only peers: select Cal for general tasks,
Mark for a mechanical-design conversation, or Reviewer for a review-only
session. They are the only user-selectable fleet agents; Cal is the default.
Planner, Research, Frontend, and Worker are subagent-only leaves and cannot
launch further agents. The delegation paths are:

```text
You -> Cal                      You -> Mark                      You -> Reviewer
       |-- Planner                     `-- Research
       |-- Research
       |-- Frontend
       `-- Worker
```

Cal, Mark, and Reviewer cannot launch one another. Mark may delegate only to
read-only Research; it owns authorized implementation directly. Reviewer is
review-only and cannot launch agents. Research and Worker are
leaf agents and cannot launch further agents. Cal can use Research for evidence,
Planner for broader investigation, Frontend for frontend planning and review,
and Worker for implementation. A persistent workflow controller is not included
yet; neither primary should imply durable background orchestration.

Cal's delegation permissions and Planner's permissions are in
`fleet/opencode.jsonc`; Mark's, Frontend's, Research's, Reviewer's, and
Worker's tool permissions are in their agent definitions. Mark's definition
permits editing source and supporting project files, including Python, and
running shell commands while denying other actions by default. Reviewer's
definition denies editing and general shell access by default and permits only
the exact hardened Git inspection invocations listed in
[Hardened Git inspection permissions](#hardened-git-inspection-permissions),
read/search tools, web evidence tools, the `cad-review` skill, and user
questions; it cannot implement fixes or run builds and tests. Frontend and
Planner use the same exact hardened Git inspection invocations and deny all
other shell access: Frontend by its agent definition, Planner by the complete
fleet config. The complete config replaces each device's OpenCode config as
described below. On an existing installation, remove any
legacy Cal delegation allowance for the former agent; Mark is primary-only and
must not be a Cal child. Update the fleet agent definitions and shared
instructions.

Agents whose definitions grant read-all (Reviewer, Frontend, Research, and
Mark) restore the base policy's sensitive-file asks for `*.env` and `*.env.*`
files, which the read-all grant would otherwise override. This constrains the
read tool only: it does not sandbox Mark's shell access, which is permitted
broadly by design, and it does not change the specialists' intended roles.

The shared configuration disables the built-in Build and Plan agents. Disable
any additional local primary agents in that device's config to keep its picker
limited to Cal, Mark, and Reviewer; their files do not need to be deleted. Do not mark the
specialists hidden: `mode: subagent` prevents primary selection while retaining
them in the permitted delegation catalogs.

### Mark workflow

Mark owns the conversation with the user: clarify design intent, research
constraints, propose a design, and define feature boundaries and geometric
acceptance criteria. Research can supply vendor, standards, or material evidence
when needed. Within the user-authorized scope, Mark directly implements the
authoritative CAD source and supporting project files, including Python source,
configuration, design/provenance documentation, and manifests; Mark runs builds
and exports, and verifies results against the agreed design. Cal can suggest switching to Mark, but does not launch it or
silently transfer the conversation.

Design discussion, research, a completed plan, or tool-access approval alone
does not authorize implementation. Mark presents the proposed design and
material unresolved choices and obtains authorization before implementation,
unless the user has already explicitly authorized that scope. Routine corrections
within the approved scope do not require repeated approval. If Research reports
blocking questions, missing access, or evidence gaps, Mark resolves them with the
user before resuming affected work; do not rely on the user finding a question in
a separate child-session conversation.

Mark must load the `cad` skill for CAD work. The skill emphasizes one
authoritative master, independently removable feature modules, and source-level
changes rather than code or geometry layered over obsolete results. Explicit
feature flags or clearly commented-out feature calls are acceptable;
compensating repair chains are not. Mark's permissions allow edits to CAD source
and supporting project files, plus shell commands; they do not authorize work
beyond the agreed scope, edits to protected references without authority,
destructive actions, or operating a live CAD application without explicit
authority. Report exactly which builds and checks were run. Source and nominal
CAD checks do not establish physical qualification. Keep hardware details and
revision-specific decisions in each project's own `AGENTS.md`.

Child agents use their own permissions, not a subset of their parent's. A
read-only primary or a shallow delegation tree is not a sandbox or a design
approval gate. Neither primary may approve tool access on the user's behalf or
route around denied access. Check question and permission handling in the
actual client before relying on it: confirm a primary question is answerable,
a child blocker returns to the primary, and a child tool-access request remains
pending until the user acts. Configuration and prompt checks alone do not
establish that end-to-end behavior.

### Reviewer workflow

Reviewer is a user-selectable primary agent for review-only sessions. It
assesses plans, implementation, and operations and reports evidence-backed,
severity-ordered findings with concrete file/line or artifact evidence, impact,
and a practical suggested correction. It does not implement fixes, cannot
launch agents, and is not launched by Cal or Mark; the user selects it for a
review conversation.

Reviewer's permissions deny editing and general shell access and permit only
the exact hardened Git inspection invocations listed in
[Hardened Git inspection permissions](#hardened-git-inspection-permissions),
read/search tools, web evidence tools, the `cad-review` skill, and user
questions. It therefore
cannot run builds, tests, or exports, or operate a live CAD application; where
a finding depends on an executed check, it states that the check was not run
and names who is authorized to run it. For CAD work, Reviewer loads the
`cad-review` skill, which separates safe read-only inspection of source,
artifacts, and reports from builds and tests that write files or operate live
CAD.

Selecting Reviewer does not change an existing session's stored model; see
the model-selection notes under fleet models. A review confirms findings
against recorded evidence; it does not by itself verify that builds or tests
pass.

### Hardened Git inspection permissions

Reviewer's definition denies editing and general shell access and permits only
these exact hardened Git inspection invocations. Cal's entry in the
complete fleet config permits the same exact forms after a deny-all shell rule;
Frontend's agent definition and Planner's entry use the same forms and deny all
other shell access:

```text
git --no-optional-locks -c core.fsmonitor=false status
git --no-pager diff --no-ext-diff --no-textconv
git --no-pager diff --no-ext-diff --no-textconv --stat
git --no-pager diff --no-ext-diff --no-textconv --cached
git --no-pager log --no-ext-diff --no-textconv --oneline
git --no-pager log --no-ext-diff --no-textconv
```

OpenCode matches shell resources against scanner-produced command strings with
simple whole-value wildcards, so `git diff *` would also permit mutating
options such as `--output=...` and configured external diff, textconv, and
pager helpers, which execute arbitrary commands. The exact forms above disable
the known command-execution paths git consults for inspection commands
(verified on 2026-10-30 against a repo configured with a hostile external diff
driver, textconv filter, and fsmonitor hook: the plain forms ran the external
driver and hook, the hardened forms did not; `--no-optional-locks` requires
git 2.16+, verified on git 2.56.0). Any other command or form is denied or asks, so these
agents must copy these invocations verbatim and cannot substitute options.

This is a constraint on the allowlist, not a complete security sandbox: the
permission rule matches the exact command text and does not verify git's
behavior, and git still honors other configuration. The exact invocations are
harmless, but no claim is made that they cannot fail in a hostile repository.
`scripts/ship/check` enforces this shape for agent definitions that cannot edit
(Reviewer, Frontend, and Planner's config entry), checks Cal's configuration
allowlist against the commands documented in `fleet/agents/cal.md`, and checks
read-all agents' env-file restore rules.

### Fleet models and context budgets

Every fleet agent explicitly selects a shared OpenRouter alias defined in
`fleet/opencode.jsonc`; none inherits an arbitrary caller model by default:

| Local alias | Upstream OpenRouter model | Agents |
| --- | --- | --- |
| `openrouter/sol-256k#medium` | `openai/gpt-6.2-sol` with medium reasoning | Cal |
| `openrouter/sol-256k#high` | `openai/gpt-6.2-sol` with high reasoning | Planner, Mark |
| `openrouter/muse-ember-270k#max` | `meta/muse-ember` with max reasoning | Research, Worker |
| `openrouter/kimi-k3-270k#high` | `moonshotai/kimi-k3` with high reasoning | Frontend |
| `openrouter/claude-opus-5.5-270k#high` | `anthropic/claude-opus-5.5` with high reasoning | Reviewer |
| `openrouter/sol-270k` | `openai/gpt-6.1-sol` | None (alias kept available) |
| `openrouter/terra-270k` | `openai/gpt-6.1-terra` | None (alias kept available) |
| `openrouter/luna-270k` | `openai/gpt-6-luna` | None (alias kept available) |
| `openrouter/glm-5.3-flash-270k` | `z-ai/glm-5.3-flash` | None (alias kept available) |

Research and Worker share Muse Ember with max reasoning rather than
inheriting a potentially different or unbounded caller model. Frontend
retains Kimi K3 and its existing high-reasoning selection; it is not upgraded to
K3.1 Pro.
Reviewer selects Claude Opus 5.5's `high` reasoning variant, which matches the
catalog's default effort for that model, and pins the versioned catalog ID
`anthropic/claude-opus-5.5` rather than the moving `~anthropic/claude-opus-latest`
alias. The models stay versioned rather than following moving Latest aliases. Shared
definitions keep limits, capabilities, reasoning variants, and pricing estimates
in one place for each model instead of duplicating a definition per agent.

The 270k aliases have a 270,000-token context/input budget and a 32,000-token
response ceiling; `sol-256k` instead works within a 256,000-token window
with a 156,000-token maximum prompt and a 100,000-token output cap. The fleet
config explicitly enables automatic compaction; keep it
enabled when relying on these budgets. The response allowance is within the
context window, not extra on top. Actual input headroom is smaller because
OpenCode reserves space for output and compaction.

The GLM 5.3 Flash alias stays defined in the fleet config even though no fleet
agent selects it by default, so devices or sessions that still reference it
keep working. OpenRouter's GLM 5.3 Flash catalog entry (`z-ai/glm-5.3-flash`),
checked on 2026-10-30, advertises 1,048,576 context tokens, text/image/video
input, text output, tool support, and required reasoning with `low`, `high`, or
`max` effort (default `max`). Its top provider reports a 1,048,575-token context
and up to 943,717 completion tokens. The fleet alias deliberately caps its
context/input at 270,000 and output at 32,000 to match the other fleet models. The catalog lists
$0.15/M input, $0.50/M output, and $0.03/M cached input; no context-based price
tier is listed for this model. These are catalog estimates and may vary by
provider route or change over time.

The catalog and OpenRouter model metadata checked on 2026-10-26 place Sol's and
Luna's higher context-pricing tier at 272,000 prompt tokens. Kimi K3 advertises
no context-based tier in the current metadata; its 270k cap is a consistent
working budget, not a claim about a pricing threshold. Pricing estimates are
snapshots and may differ by provider route or change over time.

These budgets guide compaction, not a provider-enforced request-size or spending
cap: token estimates, large tool results, compaction requests, and local
compaction overrides can affect actual billed usage. Verify real usage rather
than assuming a guaranteed price tier.

The OpenRouter catalog entry for Claude Opus 5.5 (`anthropic/claude-opus-5.5`,
canonical slug `anthropic/claude-opus-5.5-20260921`), checked on 2026-10-30,
advertises 1,000,000 context tokens, text/image/file input, text output,
mandatory reasoning with `low`, `medium`, `high`, `xhigh`, or `max` effort
(default `high`), and a top-provider completion limit of 128,000 tokens. The
fleet alias deliberately caps its working context/input at 270,000 and output
at 32,000 to match the other fleet models. The catalog lists $4/M input,
$20/M output, $0.20/M cached input, and $5/M cache write; no context-based
price tier is listed for this model. These are catalog estimates and may vary
by provider route or change over time.

Point the service at `fleet/` (see Native setup) before using the
updated agent definitions. The aliases are defined in
`fleet/opencode.jsonc` itself; there is no separate generation or copy
step. No live device configuration or credentials are changed by
editing the tracked fleet config alone — backend adoption is separate.

Selecting a primary agent by ID does not change an existing session's stored
model; the session's selected model takes precedence over the agent default.
After selecting a primary agent such as Reviewer, pick the corresponding fleet
alias in that session's model picker if the stored model differs. Explicit
per-run model overrides can also bypass the fleet
budgets. No API credentials or live device configuration belong in this repository.

## Configuration and device-specific settings

`fleet/opencode.jsonc` is the single tracked global OpenCode config,
reconciling every key of the previous global config: root
model/catalog, dormant agents, compaction, providers, ordered
permissions, LSP, all six MCP definitions, all twenty references, and
tool output. It is loaded directly from `fleet/` when
`OPENCODE_CONFIG_DIR` points there; there is no template substitution,
generation, merge, or second config. No plugins, policies, or
permission conversions were introduced; permission order and scope are
unchanged, no disabled MCP was enabled, and no deny was removed.

Host-specific values appear only as native OpenCode placeholders
(`{env:FLEET_HOME}`, `{env:FLEET_LOGIN_USER}`,
`{env:FLEET_OPENROUTER_MCP_URL}`, `{env:FLEET_UVX_PATH}`, plus the
`{file:...}` form available for file contents) and are expanded by
OpenCode at load time from the service environment (see Native setup
for names, formats, and the no-blank rule). Never replace them by
hand and never materialize a private value in the tracked file. The
global `AGENTS.md` at the config root (`fleet/AGENTS.md`) is loaded
directly; `fleet/opencode.jsonc` therefore sets no `instructions`
entry, which would duplicate it.

Keep shared, non-secret settings in `fleet/opencode.jsonc`. Store
machine-specific values and secrets in the service launch environment
or in private files outside Git (for example `{file:...}` contents),
never in this repository. No credential is stored in the fleet config:
the github MCP reads its token at launch time, the remote MCP uses
OAuth with credentials outside config, and any future header
credential should use a literal of the form `{env:MY_MCP_API_KEY}`
without materializing it. Do not commit real credentials or private
device configuration. `profiles/default.jsonc` stays empty; it is not
a second config.

## Update and uninstall

Update with `git pull` in the checkout. Because the service loads
`fleet/` directly, new or renamed definitions, skills, commands, and
config take effect on the backend's next load/reload with no rerun
step; start a new session after changing instructions. The
authenticated OpenCode web client explicitly attaches the
`fleet-web-prompt-context` skill to each prompt, so update the fleet
on the OpenCode server host (pull plus backend adoption, above)
before deploying a client version that uses it. Pulling does not by
itself set the service environment or restart the service.

To uninstall the fleet as the global root, remove
`OPENCODE_CONFIG_DIR` and the `FLEET_*` values from the service launch
environment (including any private `EnvironmentFile` those values
live in), restart the service so it falls back to the default global
config under `~/.config/opencode/`, and verify with
`opencode debug paths config`. Private runtime siblings under
`fleet/` (for example `fleet/service.json`, `fleet/cli.json`) are
not part of the tracked fleet; remove or leave them only as the
device owner directs, and never commit them.

## Add content

- Add agents as `.md` files under `fleet/agents/` with OpenCode agent
  frontmatter.
- Add skills as `fleet/skills/<skill-id>/SKILL.md`; supporting files
  alongside a skill need an explicit `.gitignore` exception (the
  fleet ignore is deny-by-default).
- Add slash commands via a server plugin under `fleet/plugins/`
  (create the directory and an explicit ignore exception if needed);
  the Markdown `fleet/commands/` directory is intentionally removed.
  The ship skill is invoked explicitly as `@ship`; no slash command
  is currently registered.
- Put reusable team conventions in `fleet/AGENTS.md`.
- Add configuration structure and policy to `fleet/opencode.jsonc`;
  host-only values stay in the private service environment as
  `{env:...}` placeholders, not in a second config.

For OpenCode itself, use the bundled OpenCode skill; the fleet ships no
repo-local `fleet/skills/opencode/` copy.

See the [OpenCode V2 documentation](https://opencode.ai/v2/docs/) for supported
configuration fields and formats.
