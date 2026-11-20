# Ship standard

Ship a staged change through Husky commit and push gates, a nested
non-prod deploy and E2E run, then an open GitHub PR for review. Cal
owns authority and user decisions; Worker runs only the fleet scripts
below. The skill is `fleet/skills/ship/SKILL.md` (ID `ship`, frontmatter
name `Ship`, `opencode/autoinvoke: false`), the `/ship` slash command
is registered by the server plugin `fleet/plugins/ship.ts`, and the PR
body template is `fleet/skills/ship/resources/PR_TEMPLATE.md`. Keep
`scripts/ship/` together.

## What exists

- `scripts/ship/ship-doctor` — read-only diagnostics (Step 1). It
  takes one explicit repository path, inspects only bounded
  allowlisted local metadata, and prints versioned JSON.
- `scripts/ship/ship-destination` — read-only destination selection
  (Step 2). Worker runs it with the repository path and, only when the
  user already named them in explicit prior instructions, an explicit
  remote and branch. It inspects the configured GitHub remote identity
  and current branch and prints versioned JSON (`selected` or
  `blocked`); a small deterministic helper is justified here because
  remote, upstream, and main-tracking resolution is easy to misread by
  hand and must be identical every run. It never writes, fetches, or
  emits a raw remote URL.
- `scripts/ship/ship-build` — validates opt-in and wiring, then
  commits the reviewed staged set and pushes to the selected remote
  and ref (Steps 2–3).
- `scripts/ship/ship-deploy` — fleet pre-push wrapper that runs the
  non-prod rollout and the full E2E suite for the exact outgoing SHA
  before upload (Step 4, nested in the push).
- `scripts/ship/check` — relocated check runner (former
  `scripts/check`), wired from the still-active `.githooks/pre-commit`
  hook. Run it with `./scripts/ship/check`.
- `/ship` via `fleet/plugins/ship.ts` — registers a fixed prompt to
  Cal that loads the skill by ID. V2 skill frontmatter cannot
  register a slash command. The plugin performs no shell or
  repository operations, rejects trailing arguments before admission
  (no prompt is admitted), and does not switch agents: on a non-Cal
  session it reports the wrong agent instead. It replaces the deleted
  Markdown command because trailing input in a Markdown or JSON
  command template would be expanded by shell interpolation outside
  the agent permission flow. Title matching and ID `ship` guard the
  registration; a pre-existing `ship` command is left in place.
- This document and `tests/ship_doctor_test.py`,
  `tests/ship_workflow_test.py`,
  `tests/ship_destination_test.py` — the one strict opt-in standard
  and the realistic Git fixtures that prove the boundary.

When the service launch environment points `OPENCODE_CONFIG_DIR` at
`fleet/` (see README Native setup), the skill and the plugin are
discovered from the fleet root. The web client does not perform
native command dispatch for this fleet; a web user loads the skill
explicitly as `@ship` with no arguments, under the same rules and the
same authorization contract: the invocation authorizes the routine
staged-only workflow through deploy, E2E, push, and PR creation, with
no routine approval stops.

## Five steps

Keep the user draft steps in the skill (`fleet/skills/ship/SKILL.md`):

- Step 1 - Run the ship-doctor script
- Step 2 - Validate the state of the current environment
- Step 3 - Run the ship-build script
- Step 4 - Run the ship-deploy script
- Step 5 - Create a PR

Step 4's deploy is nested in the Step 3 push (see Ship-deploy below);
there is no second, separate deploy run.

## The one strict opt-in standard

There is exactly **one** ship standard, adopted repository by
repository by explicit opt-in. There is **no per-repo config**, no
adapters, and no fallbacks: a repository either conforms to this
standard exactly or it does not ship. The shared ship layer never
invents a second way to pass, and a repository that cannot meet the
standard is reported as blocked or indeterminate, not accommodated.

The smallest explicit opt-in contract is: the repository passes
`scripts/ship/ship-doctor <repo>` locally, contains an executable
`scripts/ship-deploy`, and the wiring below delegates its push to the
fleet wrapper. The full conformance table is:

A conforming repository has, at its root:

| Requirement | Exact shape |
| --- | --- |
| Toolchain pin | `package.json` field `packageManager` set to a pinned `name@x.y.z` version |
| Lockfile | A non-empty lockfile corresponding to the pinned manager: npm → `package-lock.json`, pnpm → `pnpm-lock.yaml`, yarn → `yarn.lock`, bun → `bun.lock` or `bun.lockb`. A mismatched lockfile is blocked, not accepted |
| Husky dependency | `devDependencies` (or `dependencies`) declares `husky` with a non-empty version string; shape only, never executed |
| Git layout | An ordinary `.git` directory with `HEAD` and `config`; a linked worktree gitdir file, a bare repository, a symlinked `.git`, or any other layout is indeterminate |
| Declared hooks path | Git config `core.hooksPath` declares `.husky/_` exactly. Directory presence alone never passes this check |
| Pre-commit hook | `.husky/pre-commit`, a regular file (not required to be executable: Husky v9 runs user hooks via `sh`) |
| Commit-msg hook | `.husky/commit-msg`, a regular file |
| Pre-push hook | `.husky/pre-push`, a regular file delegating to `scripts/ship/ship-deploy` |
| Generated shims | `.husky/_/pre-commit`, `.husky/_/commit-msg`, `.husky/_/pre-push`, each a regular executable file |
| Husky helper | `.husky/_/h`, a regular file (sourced by the shims; not required to be executable) |
| `prepare` script | Exactly `husky` |
| `format:check` script | Present, a non-empty string (exact command is the repository owner's choice) |
| `lint` script | Present, a non-empty string |
| `test:unit` script | Present, a non-empty string |
| `test:e2e` script | Present, a non-empty string — the standard E2E entry point |
| Non-prod entry | `scripts/ship-deploy`, an executable regular file taking exactly one SHA argument |

Visible disable or override indicators in allowlisted files are a
known mismatch: `--no-verify`, `HUSKY=0`, `core.hooksPath` in
`package.json` or a hook body, and legacy `husky.hooks` declarations.
A repository that disables or overrides the gates is blocked, never
silently accepted.

Adoption must not silently drop existing gates, including Companion
checks. Adoption preserves each existing gate in an approved mapping:
every current gate is explicitly mapped to the retained check that
replaces it, and that mapping is approved by the repository owner
before adoption. Adoption also creates no unintended duplicated
hooks: the resulting hook set contains each gate exactly once, with
no duplicated hooks left behind by the adoption step.

## Husky is the only gate

A normal commit and push trigger the gates **via Husky alone**: the
pre-commit hook runs the repository's checks on commit, and the
pre-push hook runs them on push. There is no alternate gate outside
Husky — no CI-only gate, no server-side substitute, no second hook
system — and there will not be one. If Husky does not run, the gate
did not run.

`ship-build` therefore validates the effective Husky wiring —
declared `core.hooksPath`, executable generated shims, and the
standard pre-push delegation — *before* any mutation, never
executing the hook bodies to prove it. The doctor's shape check alone
does not prove the runtime ran. Effective validation is stronger than
shape: `ship-build` requires the genuine installed v9 runtime (helper
bytes and shim bytes, see Ship-build below), not a no-op shim or a
comment-only hook that merely mentions the wrapper.

## The doctor

### Interface

Execution is through the permitted executor only, using the trusted,
absolute, verified fleet installation of the doctor: the fleet-managed
script file at its absolute fleet-checkout location, verified to be
that fleet file and not a file from the target repository. A
repository-relative doctor path is never executed, because it would
resolve relative to the target's working directory and could run
target code. The invocation shape is:

```sh
<absolute-fleet-checkout>/scripts/ship/ship-doctor <repo-path>
```

- Exactly one argument: the explicit path to the repository root.
  There is no default directory and no implicit current-directory
  behaviour.
- Output is versioned JSON on stdout: `schema_version` (currently
  `1`), `tool`, `result`, `checks` (stable IDs with `pass`, `fail`, or
  `unknown` status and a stable reason code), and `not_checked`.
- Exit codes match the result: `0` for `local_pass`, `1` for
  `blocked`, `2` for `indeterminate`. A missing argument also exits
  `2`.
- Overall result precedence: any `unknown` check makes the result
  `indeterminate`; otherwise any `fail` makes it `blocked`; otherwise
  `local_pass`. Known mismatches (`fail`) are distinguished from
  unknowns (`unknown`) throughout — the doctor never guesses.

### Check IDs

`path.safety`, `layout.supported`, `metadata.parse`, `git.layout`,
`husky.hooks_path`, `husky.pre_commit`, `husky.commit_msg`,
`husky.pre_push`, `husky.shim_pre_commit`, `husky.shim_commit_msg`,
`husky.shim_pre_push`, `husky.helper`, `husky.dependency`,
`toolchain.pinned`, `toolchain.lockfile`, `disable_indicators`,
`scripts.prepare`, `scripts.format_check`, `scripts.lint`,
`scripts.test_unit`, `scripts.test_e2e`, `structure.wiring`.

### Safety properties (by construction, not by policy)

- Read-only: it never writes, never runs target code, and never
  imports anything from the target repository.
- Linux only, fail closed: traversal is anchored on directory file
  descriptors opened one component at a time from the filesystem root
  with no-follow semantics. Every symlink component — ancestor or
  in-tree — is rejected, as is every non-regular read target (for
  example a FIFO, which is opened nonblocking and rejected by fstat
  without being read). Unsupported platforms are indeterminate.
- Reads are hard-capped: each allowlisted file is read through its
  descriptor with an explicit byte cap, never unboundedly after a
  stat. Anything larger, malformed, unreadable, or non-regular makes
  the affected checks `unknown` (indeterminate) rather than being
  trusted.
- Only allowlisted files are read (`package.json`, the user hook
  files, and lockfile metadata by descriptor stat only). The single
  authorised exception is a bounded, no-follow, narrowly parsed read
  of the local declared Git hooks path in an ordinary `.git`
  directory: only `core.hooksPath` and `core.bare` are interpreted,
  includes are never resolved, and no value from that file is ever
  emitted. Any other Git config layout (includes, bare, linked,
  malformed) makes the affected checks unknown.
- Unsafe paths fail safely: a missing path, a non-directory, or any
  symlinked path component means no inspection happens at all.
- Output contains only check IDs, statuses, and reason codes. It
  never emits file contents, script commands, config or remote
  strings, or secrets. Placeholder hook bodies establish no wiring:
  the doctor checks file shape and scans bodies only for visible
  disable indicators; it never claims placeholder bodies prove the
  hooks actually run.

### What the doctor does not check

`not_checked` always lists: `effective_runtime`, `hook_execution`,
`test_suite_execution`, `git_state_and_remotes`,
`environment_and_endpoints`, and `deployment`. In particular the
doctor does not verify the effective runtime (installed Node or
package-manager versions), does not execute hooks or any suite, does
not know the suite contents or environment, and does not look at
branches, commits, or remotes. A `local_pass` means only that the
static, allowlisted shape matches the standard. The doctor is
local structural validation only, and it is not Web/native dispatch
readiness. Web or native dispatch (including any browser work) is a
separate capability with its own authorization and permissions; a
local pass establishes nothing about it.

Fixture-only tests in `tests/ship_doctor_test.py` cover each outcome,
missing and bypassed hooks, unsafe and symlinked paths, FIFO and
capped reads, malformed or untrusted metadata, unchanged fixtures,
and secret redaction. They run locally via `./scripts/ship/check`;
there are no live endpoint tests.

## Destination selection (Step 2)

Worker first runs the read-only destination helper:

```sh
<fleet-checkout>/scripts/ship/ship-destination <repo-path> [--remote <remote>] [--branch <topic>]
```

Cal passes `--remote` or `--branch` only for values the user already
named in explicit prior instructions. Otherwise the helper derives the
destination from verified repository state, in this order: explicit
prior instructions; off `main`, the current branch as topic with its
configured upstream remote when appropriate (merge ref names the same
branch), otherwise the single configured remote; on `main`, a safe
unique topic derived from the staged change (`ship/<staged-path slug>`,
suffixed until free locally and in tracking refs) with `main`'s
configured tracking remote when set, otherwise the single configured
remote. Multiple remotes with no such resolution, a mismatched
upstream, a diverting or ref-adding remote, or a remote URL that does
not parse to one GitHub owner and repository blocks with a specific
reason code. A normal `/ship` authorizes this routine derivation with
no routine approval stops: an ordinary eligible off-main topic branch
needs no confirmation, and no routine git-derived value is demanded
from the user. Staged scope and
outgoing commits are surfaced from the helper decision and do not
require reconfirmation in routine cases; an empty index is a scope
blocker, never a reason to sweep the working tree.

## Ship-build (Steps 2–3)

Worker runs with the Step 2 helper values:

```sh
<fleet-checkout>/scripts/ship/ship-build <repo-path> \
  --remote <remote> --ref refs/heads/<topic> \
  [--branch <topic>] --message <message>
```

All of remote, ref, and message are required and explicit at the
script boundary; there are no defaults. The script, in order:

1. Requires the doctor's `local_pass` (Step 1) and the executable
   opt-in (`scripts/ship-deploy`, a regular file, not a symlink).
   An inherited `HUSKY=0` blocks, `HUSKY=1` is then set explicitly,
   and a Husky init shard (`husky/init.sh` under the XDG config home)
   that sets `HUSKY=0` also blocks, because the helper sources that
   shard before its own check.
2. Validates the effective wiring before any mutation: `core.hooksPath`
   is exactly `.husky/_`, the declared and installed Husky versions
   both pin v9, `.husky/_/h` exactly matches the installed helper
   file, each shim exactly matches the runtime's generated shim, and
   `.husky/pre-push` delegates with exactly one effective line. Hook
   bodies are never executed here. A no-op shim, a stub helper, or a
   comment-only pre-push is refused. Bypass indicators block. Push
   configuration that would add refs (`remote.<name>.mirror`,
   `remote.<name>.tagOpt` of `--tags`) or divert the destination
   (`remote.<name>.pushurl`) also blocks.
3. Reserves an owned per-run evidence directory under `.git`
   (`ship-runs/<run-id>/`), refusing symlinks and pre-existing paths,
   then reviews the staged set and prints it with the outgoing commits
   (base to `HEAD`). There is no implicit staging: the staged set
   must be non-empty, the script never runs `git add`, and unstaged
   tracked changes or untracked payload make the candidate unclean
   (rejected before publish, never reported-only).
4. Compares current remote `main` on and off `main`: it fetches the
   explicit remote first (never trusting a possibly stale tracking
   ref), then counts with `refs/heads/main...remote/main` (left is
   local-only, ahead; right is remote-only, behind). Ahead or diverged
   blocks. Behind-only fast-forwards only with no rewritten commits —
   on `main` by merging the remote tip, off `main` by advancing the
   `main` ref without moving `HEAD` — and only when the staged tree
   cannot be overwritten upstream and is verified unchanged after the
   fast-forward (by staged tree, not file names alone).
5. Handles the branch. On `main` it requires `--branch <topic>` equal
   to the ref branch and creates that safe branch. Off `main`, `--branch`
   if given must equal the current branch and the ref must name the
   same branch. Work may start on `main` or off `main`; the starting
   branch and destination come from the Step 2 helper decision, never
   from a user prompt for a routine value.
6. Commits the staged set with a plain `git commit -m` (never with
   bypass flags) and records `.git/ship-runs/<run-id>/commit.json` for
   the exact candidate SHA, bound by content (run, candidate, remote,
   ref, parent, and tree). The candidate's parent must equal the
   reviewed parent and its tree must equal the reviewed staged tree.
   A failed commit gate blocks the push with gate output preserved.
7. Pushes the pinned candidate SHA (`<SHA>:<ref>`) to the explicit
   remote (this runs the real pre-push gate). The pinned form removes
   the moving-HEAD race that `HEAD:<ref>` would carry. No automatic
   retry follows a failed push. On push failure the script reconciles
   by reading the remote ref and reports what that read shows, without
   replaying or deploying again; a failure alone does not prove that
   nothing was uploaded.
8. Verifies the post-push remote SHA with `git ls-remote` against the
   candidate and requires both evidence files in the run directory
   with content matching the run, candidate, remote, and ref. A missing
   post-push receipt cannot prevent the upload that already happened;
   the script says so and fails closed on the verification, never
   claiming prevention. Tests prove this boundary with real Git
   fixtures (`tests/ship_workflow_test.py`).

The script performs no destructive cleanup and deletes nothing.

## Ship-deploy (Step 4, nested in the push)

Deployment is nested in the Step 3 push, not a second deploy. The
real `.husky/pre-push` invokes the fleet wrapper; the wrapper reads
exactly one pre-push record line on standard input, requires a single
branch push of a single full SHA (as a branch ref, `HEAD`, or the
pinned candidate SHA itself, which Git records in both local fields),
requires that SHA's fresh commit receipt to exist with content matching
the candidate, remote ref, parent, and tree, requires the candidate to
equal the current `HEAD` with a clean checkout whose tree tracks the
deploy entry and package manifest, then runs the two fixed inputs in
order:

1. Non-production rollout: `<repo>/scripts/ship-deploy <SHA>` with
   the exact outgoing SHA as the sole argument. The script must be a
   regular executable, not a symlink. Success is the single
   deterministic stdout line `SHIP_DEPLOYED_SHA=<SHA>` naming that
   SHA; any other output, no such line, a duplicate line, or a
   mismatched value blocks the push. The wrapper never infers a
   staging endpoint, never guesses from log keywords, and never runs
   arbitrary user shell snippets; there are no Companion-specific adapters.
2. Full test run: `<manager> run test:e2e` derived from the pinned
   `packageManager`, with `SHIP_TARGET_SHA` and `SHIP_DEPLOYED_SHA`
   set to the exact candidate in the environment. The suite always
   runs in full with no arguments, no filtering, and no skipping. The
   requirement is **the repository’s E2E suite must finish successfully**
   against the deployment of the exact outgoing SHA.

The wrapper also re-validates `HEAD` and the clean checkout after
deployment and test, and writes `.git/ship-runs/<run-id>/deploy.json`
(with the run, candidate, deployed SHA, remote, ref, and manager) on
success, then exits zero, allowing upload. On any failure it exits
non-zero and Git uploads nothing. Run evidence is owned and per-run
under `.git`; owners never commit it.

Race limit stated honestly: the wrapper holds no distributed lock. If
`HEAD` moves during the rollout, upload is still blocked (and the
re-check catches the move), but the rollout for that SHA may already
have happened; a concurrent push from another clone can still race the
remote. The reconcile read after transport failure reports the
observed remote ref, not a guarantee of never having uploaded.

Lease and reservation: deployment targets the repository's existing
configured non-production target only, through its own
`scripts/ship-deploy` entry. If that repository configures a lease or
reservation mechanism for the target, it runs inside the repository
entry; the fleet wrapper lets it run and invents no global reservation
system. A busy lease or an unverifiable required reservation is a
specific blocker: the wrapper preserves the repository entry's output,
the push is blocked, and the workflow reports that specific lease
reason. It never asks whether the target is in use, never polls for
the lease, and never retries by an alternate path. With no configured
lease, no lease check is invented.

## Standardized hook wiring fixture

The standardized small wiring a conforming repository commits is:

```sh
#!/bin/sh
# .husky/pre-push — delegate the real pre-push to the fleet wrapper.
exec "<fleet-checkout>/scripts/ship/ship-deploy"
```

`.husky/pre-commit` and `.husky/commit-msg` remain the repository
owner's gate commands (for example `npm run format:check`). The
generated shims and `.husky/_/h` are Husky's: each shim is exactly
`#!/usr/bin/env sh` plus sourcing of the helper, and the helper is
exactly the installed `husky` package's `husky` file (copied by install).
`tests/ship_workflow_test.py` builds this wiring as a realistic
fixture: `git config core.hooksPath .husky/_`, regular user hooks,
exact installed shims and helper with an installed v9 stub, and the
delegation line above using an absolute fleet path known to the
fixture. `ship-build` validates the effective delegation line, not a
substring inside a comment; no fixture hook is ever executed outside
its own Git push boundary.

## Before-upload guards and exact-candidate evidence

Before anything is uploaded, guards run against the exact candidate
being shipped, and the evidence recorded names that exact candidate
(its commit), not a nearby or earlier state. Evidence from one
commit never stands in for evidence about another. Fingerprint checks
at the mutation boundaries compare the parent, branch, and staged or
candidate tree rather than file names alone, and the push names the
pinned candidate SHA so a later `HEAD` move cannot change the upload.

## PR (Step 5)

Create or reuse a matching open GitHub PR for the topic branch and
ref with the permitted GitHub MCP tools. First look for the
repository pull request template (under `.github/`, top-level, or
`docs/`), keeping its wording where it exists. Cal calls `get_me`
first and fixes the exact owner, repository, base (`main`), and head
from the selected Step 2 destination before any find or create. Cleanup is a separate step before the PR:
Worker removes only the single owned per-run directory under `.git`
for this run, after the candidate and remote ref have been copied into
the draft, verifying the path is the expected run directory and not a
symlink. Duplicate-safe find, create, and requery follows: list open
pull requests for the exact head and base, reuse exactly one match,
create exactly one when none matches, stop on more than one, then
requery the detail. Verify the actual pull request: open state, its
own head SHA equal to the candidate, and URL present — the pull
request's own head SHA and the remote ref SHA from `git ls-remote`
are verified separately and must agree. When a PR result is ambiguous,
query again before any retry. Then return clean to local `main`,
leaving the topic branch intact, via Worker's guarded checks of a
clean status, the switch itself, and the branch confirmation. There
is no merge here. Cal uses only the permitted hardened inspection
invocations; Worker runs only the named switch and cleanup
operations. Never push by an alternate path.

## Staging, branches, and synchronization

- Work may start on `main` or off `main`. The starting branch and
  destination come from the Step 2 helper decision; an ordinary
  eligible off-main topic branch needs no confirmation.
- Staged scope only: shipping acts on the staged, intended change
  set. There is no implicit staging — unstaged or untracked work is
  never swept in, and an empty index is a scope blocker.
- Selected remotes and refs: `ship-build` takes the Step 2 helper
  values explicitly. There is no destructive cleanup.
- Ahead or diverged policy applies to local main, not to all feature
  branches: a local main that is ahead of or diverged from its
  upstream blocks. A feature branch being ahead of its base is
  normal (it carries its own commits) and is not by itself a block.
- Behind-only automatic sync applies to local main on and off the
  starting branch: a local main that is only behind may be synced
  automatically, and only with no rewritten commits — fast-forward
  style updates that preserve every existing commit and the staged
  work (verified by staged tree). Any need to rewrite history
  is a block, not an action.
- No merge: shipping opens or reuses a pull request for the branch
  and then returns clean to local main, leaving the topic branch
  intact (the topic branch is not deleted). Closeout never deletes
  unrelated or pre-existing work.
- Fail closed: bypass, missing, or failed evidence stops the ship.
  There are no auto retries of external mutations.

## Companion adoption checklist

A repository becomes ship-ready when it meets the opt-in contract
above. Readiness is current and verified per attempt by Cal. To
become ship-ready, the owner, in order: makes the tree clean on a named
branch (on `main` or off `main`, resolved by the Step 2 helper); meets the strict
standard so `scripts/ship/ship-doctor <repo>` reports `local_pass`;
installs the pinned Husky v9 runtime and verifies the helper, shims,
and the single-line pre-push delegation; adds executable
`scripts/ship-deploy` with the one-SHA contract and the single
`SHIP_DEPLOYED_SHA` line; wires `.husky/pre-push` to the fleet
`scripts/ship/ship-deploy` wrapper above; keeps run evidence under
`.git` and never commits it; and runs the realistic fixtures in
`tests/ship_workflow_test.py` until a real push of an exact candidate
succeeds. Production deployment stays separate (see below).

## Web/native dispatch and permissions

Dispatching work to a browser or a native client (Web/native
dispatch), and the permissions that allow it, are a separate
capability with its own explicit authorization and permission review.
A local pass is never reported as dispatch readiness. For `/ship`
itself, a web user types `@ship` with no arguments to load the skill
when the custom client does not dispatch the native command; the
agent then follows the fixed Cal-owned workflow above under the same
authorization contract as `/ship` (routine staged-only ship with no
routine approval stops).

## Production deployment stays separate

Production deployment stays separate. This ship standard never
deploys to production and never substitutes for the former
production deploy skill workflow (`fleet/skills/deploy/SKILL.md`,
intentionally deleted) or its `scripts/deploy` entry point
(intentionally deleted), neither of which may be reintroduced.

## Verification

`./scripts/ship/check` validates the scripts' shell syntax and
ShellCheck diagnostics, the doctor's and destination helper's Python
syntax, and the read-only shape of both helpers, runs the fixture-only
test suite (`tests/ship_doctor_test.py`, `tests/ship_workflow_test.py`,
`tests/ship_destination_test.py`),
validates the fleet JSON/JSONC configuration and ignore allowlist,
and checks this document, the skill
(`fleet/skills/ship/SKILL.md`), the plugin (`fleet/plugins/ship.ts`),
and the PR template against the standard described here. The skill
contains no OpenCode shell interpolation marker (the
exclamation-and-backtick marker), no other interpolation, and no
repository-relative doctor execution. Run it with
`./scripts/ship/check`.

Untested areas stated honestly: the ambiguous-transport reconcile
(a push that fails after the remote has accepted the ref) has no
local-bare reproduction and is covered by code path only, not by a
fixture upload; and the live Step 5 orchestration that creates a real
GitHub pull request against a live remote is not covered by a fixture
(a faked pull request object is never substituted for that live
claim), while the duplicate-safe identity checks and the pull request
head versus remote-ref distinction are exercised by the debilled
plugin dispatch tests and the Git fixtures.
