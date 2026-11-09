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
For a rename, remove an old symlink only after confirming it points to the removed
fleet-managed source file; the installer never removes unmanaged assets.

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

The fleet defines seven agents under `fleet/agents/`:

| Agent | Model | Context / response budget | Role |
| --- | --- | --- | --- |
| **Cal** (`cal`) | GPT-6.1 Terra, medium reasoning | 270k / 32k | Conversational companion and coordinator |
| **Planner** (`planner`) | GPT-6.1 Sol | 270k / 32k | Read-only investigation and concise task plans |
| **Research** (`research`) | GPT-6 Luna | 270k / 32k | Read-only, evidence-driven web and repository research |
| **Frontend** (`frontend`) | Kimi K3, high reasoning | 270k / 32k | Read-only frontend planning and review; no code edits |
| **Mark** (`mark`) | GPT-6.1 Sol | 270k / 32k | Primary mechanical-design lead; authorized CAD-source and supporting-file edits, builds, and verification |
| **Reviewer** (`reviewer`) | Claude Opus 5.5, high reasoning | 270k / 32k | Review-only primary; evidence-backed review of plans and work, CAD via the `cad-review` skill |
| **Worker** (`worker`) | GPT-6 Luna | 270k / 32k | Implementation, operations, and verification |

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
other shell access: Frontend by its agent definition, Planner by the shared
configuration fragment. Merge the
configuration fragment into each device's OpenCode config as described below. On an existing installation, remove any
legacy Cal delegation allowance for the former agent; Mark is primary-only and
must not be a Cal child. Update the linked agent definitions and shared
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
configuration fragment permits the same exact forms after a deny-all shell rule;
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
`scripts/check` enforces this shape for agent definitions that cannot edit
(Reviewer, Frontend, and Planner's config fragment), checks Cal's configuration
allowlist against the commands documented in `fleet/agents/cal.md`, and checks
read-all agents' env-file restore rules.

### Fleet models and context budgets

Every fleet agent explicitly selects a shared OpenRouter alias defined in
`fleet/opencode.jsonc`; none inherits an arbitrary caller model by default:

| Local alias | Upstream OpenRouter model | Agents |
| --- | --- | --- |
| `openrouter/terra-270k#medium` | `openai/gpt-6.1-terra` with medium reasoning | Cal |
| `openrouter/luna-270k` | `openai/gpt-6-luna` | Research, Worker |
| `openrouter/sol-270k` | `openai/gpt-6.1-sol` | Planner, Mark |
| `openrouter/kimi-k3-270k#high` | `moonshotai/kimi-k3` with high reasoning | Frontend |
| `openrouter/glm-5.3-flash-270k` | `z-ai/glm-5.3-flash` | None (alias kept available) |
| `openrouter/claude-opus-5.5-270k#high` | `anthropic/claude-opus-5.5` with high reasoning | Reviewer |

Research's explicit Luna default matches the usual Cal-led delegation instead
of inheriting a potentially different or unbounded model. Worker also selects
Luna, reusing the same shared alias rather than defining a second copy. Frontend
retains Kimi K3 and its existing high-reasoning selection; it is not upgraded to
K3.1 Pro.
Reviewer selects Claude Opus 5.5's `high` reasoning variant, which matches the
catalog's default effort for that model, and pins the versioned catalog ID
`anthropic/claude-opus-5.5` rather than the moving `~anthropic/claude-opus-latest`
alias. The models stay versioned rather than following moving Latest aliases. Shared
definitions keep limits, capabilities, reasoning variants, and pricing estimates
in one place for each model instead of duplicating a definition per agent.

Each alias has a 270,000-token context/input budget and a 32,000-token response
ceiling. The fleet fragment explicitly enables automatic compaction; keep it
enabled when relying on these budgets. The response allowance is within the
context window, not an extra 32k on top. Actual input headroom is smaller because
OpenCode reserves space for output and compaction.

The GLM 5.3 Flash alias stays defined in the fragment even though no fleet
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

Merge all six provider alias entries and the compaction setting into each
device's live config before using the updated agent definitions. Installing
Markdown/symlinks alone does not define the aliases. The former CAD-only
`cad-sol-270k` alias has been replaced by shared `sol-270k` in this repository;
an already-installed device needs the new alias as well as the updated agent.
No live device configuration or credentials are changed by editing this fragment.

Selecting a primary agent by ID does not change an existing session's stored
model; the session's selected model takes precedence over the agent default.
After selecting a primary agent such as Reviewer, pick the corresponding fleet
alias in that session's model picker if the stored model differs. Explicit
per-run model overrides can also bypass the fleet
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

Update with `git pull`, then rerun the installer to link newly added files. The
authenticated OpenCode web client explicitly attaches the
`fleet-web-prompt-context` skill to each prompt, so install/update the fleet on
the OpenCode server host before deploying a client version that uses it. The
installer links skills under the configured OpenCode `skills/` directory; it
does not install or restart the OpenCode server. To uninstall, remove the
symlinks the installer created from the OpenCode config directory and remove
only the marked the-team block from its global `AGENTS.md`. The installer does
not remove files on its own.

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
