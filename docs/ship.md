# Ship standard (milestone 1: diagnostics only)

> **Shipping is not implemented yet.** This document describes the one
> strict opt-in standard, the read-only doctor that can diagnose it,
> and the future pipeline that is intentionally *not* built yet. No
> part of the future pipeline below is available today.

## What exists in milestone 1

- `scripts/ship-doctor` — a read-only, standalone Python (stdlib only)
  diagnostic. It takes one explicit repository path, inspects only
  bounded allowlisted local metadata, and prints versioned JSON.
- `fleet/commands/ship.md` — the prompt-only `/ship` command. It runs
  diagnostics only if execution is permitted; otherwise it reports the
  diagnostics as not run. It makes no changes.
- This document — the standard both of the above describe.

The existing fleet installer already links everything under
`fleet/commands/` into the OpenCode user config, so `/ship` becomes
available after a normal install with no installer change. Nothing in
milestone 1 installs, deploys, or alters any live configuration.

## The one strict opt-in standard

There is exactly **one** ship standard, adopted repository by
repository by explicit opt-in. There is **no per-repo config**, no
adapters, and no fallbacks: a repository either conforms to this
standard exactly or it does not ship. The shared ship layer never
invents a second way to pass, and a repository that cannot meet the
standard is reported as blocked or indeterminate, not accommodated.

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
| Pre-push hook | `.husky/pre-push`, a regular file |
| Generated shims | `.husky/_/pre-commit`, `.husky/_/commit-msg`, `.husky/_/pre-push`, each a regular executable file |
| Husky helper | `.husky/_/h`, a regular file (sourced by the shims; not required to be executable) |
| `prepare` script | Exactly `husky` |
| `format:check` script | Present, a non-empty string (exact command is the repository owner's choice) |
| `lint` script | Present, a non-empty string |
| `test:unit` script | Present, a non-empty string |
| `test:e2e` script | Present, a non-empty string — the standard E2E entry point |

Visible disable or override indicators in allowlisted files are a
known mismatch: `--no-verify`, `HUSKY=0`, `core.hooksPath` in
`package.json` or a hook body, and legacy `husky.hooks` declarations.
A repository that disables or overrides the gates is blocked, never
silently accepted.

## Husky is the only gate

A normal commit and push trigger the gates **via Husky alone**: the
pre-commit hook runs the repository's checks on commit, and the
pre-push hook runs them on push. There is no alternate gate outside
Husky — no CI-only gate, no server-side substitute, no second hook
system — and there will not be one. If Husky does not run, the gate
did not run.

This has a direct corollary for the future pipeline: evidence that a
pre-push transport actually completed (for example a real timeout
proof from the push itself) must come from that pre-push hook path.
Shipping must not invent a separate transport gate to stand in for it.

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
<absolute-fleet-checkout>/scripts/ship-doctor <repo-path>
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
separate future capability with its own authorization and
permissions; a local pass establishes nothing about it.

Fixture-only tests in `tests/ship_doctor_test.py` cover each outcome,
missing and bypassed hooks, unsafe and symlinked paths, FIFO and
capped reads, malformed or untrusted metadata, unchanged fixtures,
and secret redaction. They run locally via `scripts/check`; there
are no live endpoint tests.

## Future pipeline (not implemented)

Everything in this section is a design constraint for later
milestones, not available behaviour. No command today stages,
commits, pushes, or deploys anything.

### Before-upload guards and exact-candidate evidence

Before anything is uploaded, guards must run against the exact
candidate being shipped, and the evidence recorded must name that
exact candidate (its commit), not a nearby or earlier state. Evidence
from one commit must never stand in for evidence about another.

### Push deploys to non-production, then E2E must finish

When shipping exists, a push deploys the exact outgoing commit to a
non-production (staging) environment first, and only then requires
that **the repository’s E2E suite must finish successfully** against
that deployment. That sentence is the requirement, verbatim. The
contract is owner-controlled and plain: the E2E suite is whatever the
repository owner's `test:e2e` entry point runs, the shared ship layer
does **not** classify individual tests, does not ask which tests to
run, and does not skip any test. It observes only whether the suite
finished successfully.

### Adoption must not silently drop existing gates

Adopting this standard must not silently drop existing gates,
including Companion checks. Adoption preserves each existing gate in
an approved mapping: every current gate is explicitly mapped to the
retained check that replaces it, and that mapping is approved by the
repository owner before adoption. Adoption also creates no unintended
duplicated hooks: the resulting hook set contains each gate exactly
once, with no duplicated hooks left behind by the adoption step.

### Staging, branches, and synchronization

- Work starts on main normally; ask the user only if starting off main.
  The starting branch is never assumed silently.
- Staged scope only: shipping acts on the staged, intended change
  set. There is **no implicit staging** — unstaged or untracked work
  is never swept in.
- Ahead or diverged policy applies to local main, not to all feature
  branches: a local main that is ahead of or diverged from its
  upstream blocks. A feature branch being ahead of its base is
  normal (it carries its own commits) and is not by itself a block.
- Behind-only automatic sync applies to local main: a local main that
  is only behind may be synced automatically, and only with
  no rewritten commits — fast-forward style updates that preserve every
  existing commit. Any need to rewrite history is a block, not an
  action.
- No merge: shipping opens or reuses a pull request for the branch
  and then returns clean to local main, leaving the topic branch
  intact (the topic branch is not deleted). Closeout never deletes
  unrelated or pre-existing work.

### Future browser dispatch and permissions

Dispatching work to a browser or a native client (Web/native
dispatch), and the permissions that allow it, are future work. They
require their own explicit authorization and permission review;
milestone 1 grants neither, and the doctor neither uses nor checks
any dispatch path. Local structural validation must never be
reported as dispatch readiness.

### Production deployment stays separate

Production deployment is governed by the separate production deploy skill
(`fleet/skills/deploy/SKILL.md`), with its own explicit user
authorization, its own standardized `scripts/deploy` entry point, and
its own reporting. This ship standard never deploys to production,
never substitutes for that skill, and never implies its authorization.

## Verification

`scripts/check` validates the doctor's Python syntax, enforces its
no-forbidden-mechanisms shape, runs the fixture-only test suite, and
checks this document and the `/ship` command against the standard
described here. The `/ship` command is prompt-only: it must contain
no OpenCode shell interpolation marker (the exclamation-and-backtick
marker), no other interpolation, and no repository-relative doctor
execution. Run it with `./scripts/check`.
