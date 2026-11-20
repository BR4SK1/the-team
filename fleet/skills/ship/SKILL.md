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
or retry a failed external mutation. Where this skill names a Cal check
with Git, Cal uses only the exact hardened inspection invocations
documented in `fleet/agents/cal.md`; any other form is denied and is
reported. Where this skill names a Worker shell invocation, Worker runs
exactly that invocation and no broader form.

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
  On success it prints exactly one stdout line of the form
  `SHIP_DEPLOYED_SHA=<SHA>` naming the SHA it rolled out; the fleet
  wrapper accepts only that deterministic line, never a log-keyword
  guess.
- `package.json` contains a non-empty `test:e2e` script, the fixed test
  input. The shared ship layer observes only whether that suite
  finishes successfully; it never skips, filters, or judges individual
  tests. The suite is run in full with `SHIP_TARGET_SHA` and
  `SHIP_DEPLOYED_SHA` in the environment, both set to the exact
  candidate SHA. The repository's E2E suite must finish successfully
  against the deployment of the exact candidate SHA.
- `.husky/pre-push` delegates with exactly one effective line to the
  fleet wrapper `scripts/ship/ship-deploy` (see `docs/ship.md` for the
  standardized wiring fixture). A comment mentioning the wrapper path
  is not a delegation. The fleet wrapper calls the two fixed inputs above
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
  candidate unclean; untracked files are rejected before publish and
  are never swept into the candidate.
- Starting branch, named explicitly. On `main`, shipping creates a
  safe topic branch (Step 3 requires the branch name explicitly). Off
  `main`, Cal asks the user first and never assumes the starting
  branch silently. An inappropriately named or wrong branch stops
  here, before any mutation.
- `main` synchronization state. A local `main` that is ahead of or
  diverged from the current remote `main` blocks. A local `main` that
  is only behind may be fast-forwarded only when the fast-forward is
  safe and preserves the staged work; otherwise it blocks. The check
  runs on and off `main` against a freshly fetched remote `main`, with
  correct ahead and behind counts. A feature branch being ahead of its
  base is normal and is not by itself a block.
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

`ship-build` validates the doctor result, the genuine installed Husky
v9 runtime (helper bytes and shim bytes), the effective pre-push
delegation, inherited Husky init, and the push configuration, before
any mutation. It then commits the reviewed staged set with a plain
`git commit` (never with bypass flags) and pushes to the explicit
remote and ref. The push uses the exact pinned candidate SHA in the
refspec, so a HEAD that moves between commit and push cannot change
what is uploaded. Husky alone runs the commit gates (pre-commit,
commit-msg) and the push-time deploy gate. The script prints the
staged stat, the outgoing commit list, and the run identity, preserves
hook and gate output, and performs no automatic retry of a failed push
or mutation. After a push failure it reconciles by reading the remote
ref without replaying or deploying again; a failed push alone does not
prove that nothing was uploaded. It performs no destructive cleanup.

## Step 4 - Run the ship-deploy script

Do not run deployment as a second, separate deploy. Deployment is
nested in the Step 3 push: the real `.husky/pre-push` hook calls

```sh
<fleet-checkout>/scripts/ship/ship-deploy
```

with the Git pre-push record on standard input. `ship-deploy` extracts
the single exact outgoing SHA, runs `<repo>/scripts/ship-deploy <SHA>`
for the non-production rollout, verifies the single deterministic
`SHIP_DEPLOYED_SHA` line naming that SHA, then runs the full owner
`test:e2e` suite against that deployment with `SHIP_TARGET_SHA` and
`SHIP_DEPLOYED_SHA` set to the candidate. The repository's E2E suite
must finish successfully. Both succeed before Git uploads anything;
any failure exits non-zero and blocks the push. The shared layer does
not classify tests and does not ask which tests to run: the whole
`test:e2e` suite runs every time. Receipt content, not a filename, binds
the run to the candidate, remote, and ref.

A post-push check that evidence is missing cannot prevent an upload
that already happened. `ship-build` reports a post-push verification
failure as such and never claims prevention after the fact.

## Step 5 - Create a PR

Create or reuse a matching open GitHub pull request for the topic
branch and ref with the permitted GitHub MCP tools. Cal owns the
decision and the identity checks; Worker performs only the guarded
operations named below. There is no merge in this step.

1. Look for the repository pull request template before filling the
   body. Worker lists the candidates (for example a pull request
   template under `.github/`, a top-level pull request template, or a
   template under `docs/`) and returns their paths. Cal keeps the
   repository wording where it exists and fills it with the shipped
   evidence below. The fleet body is
   `fleet/skills/ship/resources/PR_TEMPLATE.md` and is the only
   intended tracked resource; never track run evidence.
2. Cal first calls `get_me` (GitHub MCP) to establish the authenticated
   identity, respecting the permission flow, and stops on any denial.
   Cal then fixes the exact identity to use for every later call: the
   owner and repository parsed from the explicit remote URL, the base
   branch `main`, and the head branch and ref for the topic branch
   pushed in Step 3. No other owner, repository, base, or head is
   substituted.
3. Artifact cleanup is a separate step before the PR, after the
   candidate SHA, run identity, and verified remote ref have been
   copied into the PR draft. Worker removes only the single owned
   per-run directory under `.git` for this run (the run directory named
   by `ship-build` output). Worker verifies that the path is the
   expected run directory, is a directory, and is not a symlink, then
   removes that one directory only. Worker never removes broad paths,
   other runs, or any other owner's data. Before opening the PR,
   distinguish Git-clean state from run artifacts: run evidence under
   `.git` is not committed and must never be committed.
4. Duplicate-safe find, create, and requery. Cal lists pull requests
   for the exact owner, repository, head, and base with the GitHub MCP
   listing tool. If exactly one open pull request matches, reuse it.
   If none matches, create exactly one with the exact owner,
   repository, base, head, title, and body. If more than one matches,
   stop and requery before any retry; never guess and never create a
   second pull request by an alternate path. After any find or create,
   Cal requeries the pull request detail to confirm the result instead
   of trusting the create response alone.
5. Verify the actual pull request, not an assumed one. Cal checks the
   pull request detail for three facts: the pull request is open, its
   own head SHA equals the exact tested candidate SHA from the commit
   and deploy evidence, and its URL is present. The pull request head
   SHA (the PR object's own head) and the remote ref SHA (from
   `git ls-remote` in Step 3) are verified separately and must agree
   with the candidate; they are never conflated into one check. When a
   query result is ambiguous, query again before any retry; never guess.
6. Return clean to local `main`, leaving the topic branch intact.
   Worker checks a clean tree with `git status --porcelain --untracked-files=all`
   and requires an empty result, then checks out `main` with
   `git switch main`, then confirms the branch is `main` with
   `git branch --show-current`. Cal inspects the result with only the
   permitted hardened inspection invocations. If the tree is not
   clean, Worker does not switch and the block is returned to Cal. The
   topic branch is not deleted.

## Owner adoption checklist

A repository becomes ship-ready when it meets the opt-in contract
above. Readiness is current and is verified per attempt by Cal; a past
state does not prohibit ship after adoption. To become ship-ready, in
order: make the tree clean on a named branch (off-main requires an
explicit user ask); meet the strict standard so
`scripts/ship-doctor <repo>` reports `local_pass`; install the pinned
Husky v9 runtime and verify the helper, shims, and the single-line
pre-push delegation; add executable `scripts/ship-deploy` with the
one-SHA-argument and single `SHIP_DEPLOYED_SHA` line contract; wire
`.husky/pre-push` to the fleet `scripts/ship/ship-deploy` wrapper per
`docs/ship.md`; keep run evidence under `.git` (never commit it); and
run the realistic fixtures in `tests/ship_workflow_test.py` until a
real push of the exact candidate succeeds. Authorization stays with
Cal; Worker reports blockers rather than adapting around them.
