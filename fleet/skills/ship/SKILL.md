---
name: Ship
description: Ship a staged change through Husky commit and push gates, nested non-prod deploy and E2E, then an open GitHub PR for review
metadata:
  opencode/autoinvoke: false
---

# Ship Command

Ship a staged change to non-production and open a pull request for review.
Shipping is available only in repositories that explicitly opt in by
conforming exactly to the one strict opt-in standard in `docs/ship.md`.
A repository that cannot meet the standard is blocked, never
accommodated with a per-repository adapter, fallback, or alternate gate.

Invocation is `/ship` with no trailing arguments. The fleet server plugin
registers `/ship` and submits a fixed prompt to Cal that loads this skill
(ID `ship`, frontmatter name `Ship`) by ID. The plugin performs no shell
or repository operations, rejects any trailing argument before admission,
and does not switch agents: when the session agent is not Cal it reports
the wrong agent instead of switching. A Markdown or JSON command template
is not used, because its trailing input would be expanded by shell
interpolation outside the agent permission flow. If a custom web client
does not perform native command dispatch, the user loads this skill
explicitly by naming it in the prompt text (for example `@ship` with no
arguments); the same no-argument rule then applies. No web client code
is changed by this skill.

Cal owns authority and user decisions. Cal delegates operational steps
to Worker and never runs the scripts directly. Worker runs only the fleet
scripts named below and returns their actual output, exit status, and the
evidence SHAs. Cal must not route around a denial, bypass a failed gate,
or retry a failed external mutation.

## Opt-in contract (smallest explicit)

A ship-eligible repository satisfies all of the following, verified by
Step 1; there is no other opt-in signal:

- `scripts/ship-doctor <repo>` reports `local_pass` (exit `0`), which
  proves the strict Husky toolchain, lockfile, hooks, and script shape
  in `docs/ship.md`.
- The repository root contains an executable `scripts/ship-deploy`
  (no extension), the single deterministic non-production entry point.
  It takes exactly one argument: the outgoing candidate SHA (40 hex
  characters) as its `$1` and deploys that SHA to non-production. It
  must not infer a staging endpoint from arguments, environment, or
  configuration, and must not run arbitrary user shell snippets.
- `package.json` contains a non-empty `test:e2e` script, the fixed test
  input. The shared ship layer observes only whether that suite
  finishes successfully; it never skips, filters, or judges individual
  tests. The repository’s E2E suite must finish successfully against
  the deployment of the exact candidate SHA.
- `.husky/pre-push` delegates to the fleet wrapper
  `scripts/ship/ship-deploy` (see `docs/ship.md` for the standardized
  wiring fixture). The fleet wrapper calls the two fixed inputs above
  for the exact outgoing SHA and blocks the push until both succeed.

Production deployment and Companion-specific adapters are out of scope.
The deleted production deploy skill and its `scripts/deploy` entry point
are not used and must not be reintroduced.

## Step 1 - Run the ship-doctor script

Worker runs the trusted, absolute, verified fleet installation only:

```sh
<fleet-checkout>/scripts/ship/ship-doctor <repo-path>
```

Exactly one argument: the explicit repository root. The doctor is
read-only, never writes, never runs target code, and prints versioned
JSON (`local_pass`, `blocked`, or `indeterminate`). On `blocked` or
`indeterminate`, stop. On `local_pass`, continue to Step 2. A local pass
is static shape only; it does not prove the effective Husky runtime,
hook execution, test execution, or deployment.

## Step 2 - Validate the state of the current environment

Cal reviews the actual staged changes and any outgoing commits
before authorizing Worker. Worker collects the current environment;
Cal decides. Validation requires:

- Staged scope only. There is no implicit staging. The candidate is
  the staged set as reviewed. Unstaged tracked changes make the
  candidate unclean; untracked files are reported and never swept into
  the candidate.
- Starting branch, named explicitly. On `main`, shipping creates a
  safe topic branch (Step 3 requires the branch name explicitly). Off
  `main`, Cal asks the user first and never assumes the starting
  branch silently. An inappropriately named or wrong branch stops
  here, before any mutation.
- `main` synchronization state. A local `main` that is ahead of or
  diverged from its upstream blocks. A local `main` that is only
  behind may be fast-forwarded only when the fast-forward is safe and
  preserves the staged work; otherwise it blocks. A feature branch
  being ahead of its base is normal and is not by itself a block.
- Explicit remote and ref. The remote name and `refs/heads/<topic>`
  ref are named explicitly by the user decision; they are never
  inferred from configuration defaults.
- Effective local readiness. Worker confirms `git status`, staged
  stat, and the branch list reflect the Step 2 decision. If any
  decision is ambiguous, consequential, or denied by permissions,
  return to the user before resuming.

## Step 3 - Run the ship-build script

Worker runs:

```sh
<fleet-checkout>/scripts/ship/ship-build <repo-path> \
  --remote <remote> --ref refs/heads/<topic> \
  [--branch <topic>] --message <message>
```

`ship-build` validates the doctor result and the effective Husky
wiring (declared `core.hooksPath`, executable generated shims, and the
standard pre-push delegation) before any mutation, then commits the
reviewed staged set with a plain `git commit` (never with bypass
flags) and pushes to the explicit remote and ref. Husky alone runs the
commit gates (pre-commit, commit-msg) and the push-time deploy gate.
The script prints the staged stat and the outgoing commit list, fails
closed on bypass, missing, or failed evidence, and performs no
automatic retry of a failed push or mutation. It performs no
destructive cleanup.

## Step 4 - Run the ship-deploy script

Do not run deployment as a second, separate deploy. Deployment is
nested in the Step 3 push: the real `.husky/pre-push` hook calls

```sh
<fleet-checkout>/scripts/ship/ship-deploy
```

with the Git pre-push record on standard input. `ship-deploy` extracts
the single exact outgoing SHA, runs `<repo>/scripts/ship-deploy <SHA>`
for the non-production rollout, then runs the full owner `test:e2e`
suite against that deployment. The repository’s E2E suite must finish
successfully. Both succeed before Git uploads anything; any failure
exits non-zero and blocks the push. The shared layer does not classify
tests and does not ask which tests to run: the whole `test:e2e` suite
runs every time.

A post-push check that evidence is missing cannot prevent an upload
that already happened. `ship-build` reports a post-push verification
failure as such and never claims prevention after the fact.

## Step 5 - Create a PR

Create or reuse a matching open GitHub pull request for the topic
branch and ref with the permitted GitHub MCP tools. Fill the PR body
from `fleet/skills/ship/resources/PR_TEMPLATE.md` and track only that
intended resource. Independently verify the PR is open and that the
remote ref points at the exact tested candidate SHA (the same SHA in
the commit and deploy evidence and in `git ls-remote`). Then return
clean to local `main`, leaving the topic branch intact. There is no
merge in this step. When a PR query result is ambiguous, query again
before any retry; never guess and never push by an alternate path.

Before opening the PR, distinguish Git-clean state from run artifacts:
`.ship/evidence/` files are run artifacts under the repository's
ignore rule and are not committed. Do not delete broad paths or other
owners' data during closeout.

## Owner adoption checklist (Companion)

Companion was found dirty off-main and missing the standard
`scripts/ship-deploy`, hook wiring, and deploy adapter. Do not adopt
or run ship against it. The owner instead brings a repository to the
opt-in contract before any ship: make the tree clean on a named
branch, meet the strict standard so `scripts/ship-doctor <repo>`
reports `local_pass`, add executable `scripts/ship-deploy` with the
one-SHA-argument contract, wire `.husky/pre-push` to the fleet
`scripts/ship/ship-deploy` wrapper per `docs/ship.md`, ignore
`.ship/` evidence, and run the realistic fixtures in
`tests/ship_workflow_test.py` or the end-to-end example until a real
push of the exact candidate succeeds.
