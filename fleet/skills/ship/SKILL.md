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

Invocation is loading this skill by ID `ship` (frontmatter name `Ship`)
with no trailing arguments — explicitly as `@ship` with no arguments, or
via the skill tool with the same ID. No slash command is registered and
no plugin performs the invocation; the former plugin is removed. The
invocation itself performs no shell or repository operations, rejects
any trailing argument, and does not switch agents: when the session
agent is not Cal it reports the wrong agent instead of switching. A
Markdown or JSON command template is not used, because its trailing
input would be expanded by shell interpolation outside the agent
permission flow. No web client code is changed by this skill.

A normal ship invocation (explicit `@ship` with no arguments)
itself authorizes the routine workflow through non-production
deploy, the full E2E suite, push, and opening a pull request: the
staged-only workflow, plus the single reviewed auto-staging in Step 2
that fills an empty index on an eligible topic branch or, on `main`,
on an eligible task-owned change with established task-owned
provenance after branching to the helper-proposed topic before any
staging, so the user never stages by hand or in a terminal and no
staging is ever done on `main`.
There are no routine approval stops: neither Cal nor Worker pauses
to ask the user for a routine git-derived value (remote, branch,
ref, commit message) or to reconfirm a routine staged scope,
including the scope created by that single reviewed auto-staging.
Staging itself runs through Worker's normal permission flow for the
exact reviewed paths; that permission flow is not a separate
conversational reconfirmation and is not a separate approval of the
change. Work stops and returns to the user only on a real blocker:
a blocked or indeterminate destination (other than the handled
`staged_empty` case below, including a `staged_empty` on `main`
where task-owned provenance cannot be established), an unclean
staged scope, mixed or ambiguous work, a likely secret or unsafe
file, a scope surprise, a repository policy or authority limit, a
busy or unverifiable required lease, a failed gate, or a tool
denial. Those stops are blockers, never prompts to guess a value
or to proceed anyway.

Cal owns authority and user decisions. Cal delegates operational steps
to Worker and never runs the scripts directly. Worker runs the fleet
scripts named below, plus only the exact reviewed-path staging
invocation in Step 2 when the empty-index case applies, and returns
their actual output, exit status, and the evidence SHAs. Worker
autonomously inspects the configured GitHub remote
identity and current branch (Step 2) and derives the destination; Cal
does not demand those values from the user and does not pause for them
in routine cases. Cal must not route around a denial, bypass a failed
gate, or retry a failed external mutation. Where this skill names a Cal
check with Git, Cal uses only the exact hardened inspection invocations
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
- When `.ship/e2e-runner.json` is present in the candidate tree, the
  repository opts into isolation: a versioned, digest-pinned OCI
  contract (`isolated_oci`) read from the candidate commit and
  enforced by the fleet `scripts/ship/ship-e2e-runner`, with no
  host Node or package manager in the E2E path and no host fallback.
  When it is absent, the repository stays on the legacy host
  invocation (`legacy_host`), which is explicit migration debt and
  is never reported as isolated. Companion remains legacy until it
  migrates; this change alone does not fix Companion.
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

Worker collects the current environment and resolves the destination;
Cal decides only on a blocker. Worker runs the read-only destination
helper, the trusted absolute fleet installation only:

```sh
<fleet-checkout>/scripts/ship/ship-destination <repo-path> [--remote <remote>] [--branch <topic>]
```

Cal passes `--remote` or `--branch` only when the user already named
that value in explicit prior instructions; otherwise Worker omits both
and the helper derives the destination. The helper inspects the
configured GitHub remote identity and current branch with read-only Git
invocations only (`git --no-optional-locks`), never writes, never
fetches, and prints versioned JSON (`selected` or `blocked`, exit `0`
or `1`; exit `2` is indeterminate). On `blocked` or `indeterminate`
the workflow stops before any mutation and reports the specific
reason code, except for the single handled `staged_empty` case
below. On `selected`, Worker returns the full decision to Cal:
remote, topic, ref, GitHub owner and repository, staged files,
outgoing commits, and selection path. The helper suggests no commit
message; Step 3 crafts it.
The destination is used only when it is verified and unambiguous,
by this order:

- Explicit prior instructions first. An explicit remote and branch
  from the user win when the helper verifies them (the remote exists
  and is eligible, and the branch is safe and consistent with the
  current branch). An explicit value that conflicts with repository
  state is a blocker, never a fallback to a guessed value.
- Off `main`, the current branch is the topic. This is an ordinary
  eligible case and needs no confirmation. Its remote is the current
  branch's configured upstream remote when that upstream is
  appropriate (the upstream merge ref names the same branch),
  otherwise the single configured remote. A multiple-remote repository
  with no upstream resolution is ambiguous and blocks.
- On `main`, the helper derives a safe unique topic branch from the
  staged change (`ship/<staged-path slug>`, suffixed `-2`, `-3`, and
  so on until free locally and in the selected remote's tracking
  refs). Its remote is `main`'s configured tracking remote when set,
  otherwise the single configured remote. A multiple-remote repository
  with no main-tracking resolution is ambiguous and blocks.
- A selected remote that would divert or add refs (`pushurl`,
  `mirror`, `tagOpt --tags`), a missing remote, an upstream that
  names a different branch, or a remote URL that does not parse to
  one GitHub owner and repository blocks. Nothing is inferred from an
  unverified default, and conflicting or ambiguous destinations stop
  rather than guess.

### Empty index (`staged_empty`): inspect and stage once, then rerun

An empty index is handled once, without a routine confirmation and
without needing a terminal. The helper output already carries the
branch, `on_main`, and `scope` (`staged_empty`, unstaged tracked
paths, and non-ignored untracked paths); the helper has already
verified the branch is not detached and that local `main` exists.
On `main` with work to ship the helper also carries a fully
resolved topic proposal (remote, topic, ref, GitHub identity,
selection derived from the candidate unstaged plus untracked
paths) in the blocked `staged_empty` payload, so Worker can
branch before staging. If `staged_empty` is reported and the scope
shows work to ship (unstaged or untracked is non-empty), the case
is eligible for the one-pass reviewed staging below when either
(a) the branch is an eligible topic (not `main`), or (b) the
branch is `main` and Cal carries task-owned provenance for the
change that Worker verifies (see the `main` provenance rule
below). On an eligible case Worker inspects, coherently clears,
and stages that work as follows, then automatically reruns the
destination helper once and continues to Step 3 on `selected`.
This is the only auto-staging in the workflow; it never runs in a
loop and it never re-stages after the rerun. A clean empty scope
(no unstaged and no untracked work) is still a scope blocker:
there is nothing to ship. A `staged_empty` on `main` without
eligible provenance is likewise a scope blocker: Worker stages
nothing and creates no branch.

1. Read-only inspection with no staging yet. Worker reads the full
   tracked diffs for every unstaged path, the contents of every
   untracked path, and the outgoing commits needed to judge the set.
   Ignored files are out of scope on every path: the helper lists
   only non-ignored untracked paths, and Worker never stages an
   ignored file.
2. Coherence decision. The whole unstaged plus untracked set must
   read as one coherent change. If the work is genuinely mixed
   (unrelated changes) or ambiguous (the set cannot be judged as one
   change), Worker stages nothing and returns that mixed-work
   blocker to the user. Worker also stages nothing and returns a
   blocker when any reviewed path looks like a likely secret or otherwise unsafe to commit (for example a credential, key, token,
   or private data file, or an unreadable file) or is not a regular
   file (a symlink or other non-regular path).
3. Branch before staging on `main`. Only on `main` Worker resolves
   the helper's blocked `staged_empty` proposal (topic, ref, remote,
   GitHub identity, selection) and creates the topic branch
   carrying the reviewed edits before any `git add`:
   `git switch -c <topic>` through Worker's normal shell permission
   flow (that flow is not a separate approval of the change). Worker
   never stages on `main`: no `git add` runs while
   `git branch --show-current` is `main`. Before the switch Worker
   verifies the proposal is safe and not already present — topic
   is not `main`, matches the safe branch pattern, and
   `git show-ref --verify -q refs/heads/<topic>` fails because the
   helper suffix already ensures local and remote-tracking
   uniqueness. Worker creates exactly that helper-selected topic
   with `git switch -c <topic>` and never invents, renames, or
   picks another branch by hand. After the switch Worker verifies
   the carry: `git branch --show-current` equals the topic and is
   not `main`, `git rev-parse HEAD` equals the pre-switch HEAD, the
   index is still empty, and the unstaged tracked list
   (`git diff --name-only`) and non-ignored untracked list
   (`git ls-files --others --exclude-standard`) equal the reviewed
   sets exactly. If any carry verification fails, Worker stages
   nothing and returns a blocker; there is no stash-back loop and
   no staging before a failed carry. On a topic branch Worker
   skips this step — the checked-out branch is the topic.
4. Exact-path staging only. On a coherent, safe set Worker stages
   each reviewed path exactly as listed, one path at a time or in a
   single invocation naming exactly those paths, through Worker's
   normal permission flow (for example `git add -- <path>` repeated
   per reviewed path). Never `git add -A`, `--all`, `.`, a directory
   path, a wildcard, or any blanket add; never `git reset`,
   `git restore`, `git stash`, `git clean`, or a delete to tidy the
   tree; and never stage an ignored file or a symlink. No force is
   used and nothing deploys at staging time; staging alone never
   deploys to production either. A deleted tracked path staged this
   way records its deletion, and a rename needs both the old deleted
   path and the new path staged, so deletes and renames carry
   through. Worker first re-verifies, immediately before the first
   `git add`, that `git branch --show-current` is the topic (not
   `main`), that the index is still empty, and that HEAD is still
   the pre-switch HEAD; if the index is no longer empty or the
   branch is `main`, Worker stops and preserves that state rather
   than broadening it.
5. One rerun, then Step 3. Worker reruns the same destination
   invocation once (same repo path and same explicit `--remote` /
   `--branch` values, if any) and continues to Step 3 on `selected`,
   surfacing the now-staged files and outgoing commits without a
   routine reconfirmation. On a `main` early-branch path the rerun
   must select exactly the branch just created/checked out (same
   topic and ref, now off `main` with `on_main` false) and stage
   that exact reviewed set; if the rerun topic, staged files, or
   branch differ from the carry verification, Worker stops and
   reports the mismatch with the staged set left as staged. If the
   rerun still blocks (`staged_empty`, `scope_unclean`, an ambiguous
   remote, or any other reason), Worker stops and reports it; Worker
   never stages a second time, never broadens scope to force a
   selection, never switches back to `main` to stage, and never
   asks the user to run a terminal staging command instead.

On `main`, the same eligible empty-index case applies with
task-owned provenance, but only through branch-before-staging. A
`staged_empty` on `main` is eligible for the auto-staging above
(same read-only inspection, coherence and secret/unsafe checks,
branch creation before any staging, exact-path staging, single
rerun, and safe derived topic selection — never a publish or commit directly to `main`, and never a `git add` run on `main`)
when provenance is established before Worker branches or stages,
and it is a scope blocker otherwise. New ship-bound authorized
work that starts clean on `main` branches before editing where the
workflow can govern that; if the work was already authored
directly on `main`, Worker carries the verified edits to the
helper-proposed topic with `git switch -c <topic>` as in step 3 —
no separate approval is asked for either path.

Establishing provenance is practical, not blind. Cal carries the
task scope and a known clean baseline from the authoring context:
the known clean baseline is that the repository was clean when the
authoring work started (empty index and empty worktree, recorded
in this session's authoring context or otherwise established from
evidence), and the task-owned scope is the user-authorized change
that work was asked to make in this session. A later @ship in the same session where provenance is already
established carries that same known clean baseline and task-owned
scope forward; Cal supplies them to Worker as context and the same
branch-before-staging eligibility applies, with no routine extra
approval and no user-supplied path list required. No artificial
paperwork is required: Cal does not re-ask for a path list and the
user does not re-authorize branching or staging when clean-start
provenance and task-owned scope are already known.

Worker verifies provenance against the reviewed work before
staging: read the full unstaged plus untracked set, read the
outgoing commits as needed, and confirm that every unstaged and
untracked path fits the claimed task-owned scope from the known
clean baseline. If provenance cannot be established from the
authoring context or other evidence, or if the reviewed work does
not fit that scope — for example unrelated or pre-existing edits,
a dirty starting tree, paths outside the task scope, or an
ambiguous set that cannot be judged as one user-authorized change —
Worker stages nothing and returns a scope blocker. The ship
invocation alone is not provenance; a known clean baseline plus a
task-owned scope that is already in hand is. The convenience of
carrying that context is not permission to stage blindly:
unrelated, pre-existing, or ambiguous work is never staged on the
claim of task ownership.

When the index is already non-empty, Worker preserves that staged
scope exactly and never broadens it: Worker stages no additional
paths, even if unstaged or untracked work is present. Unstaged
tracked changes or untracked files alongside a non-empty index stay
`scope_unclean` and are rejected before publish, never hidden,
stashed, deleted, or swept into the candidate. Partially staged
changes (staged and unstaged content in the same file) are
therefore still a blocker, never silently completed.

Validation also requires:

- Staged scope, never blanket staging. The fleet scripts perform
  no implicit staging: `ship-build` still requires a non-empty
  staged set with no unstaged or untracked remainder and never runs
  `git add`. The candidate is the staged set as reviewed, including
  the single reviewed auto-staging above (empty index on a topic
  branch, or on `main` with established task-owned provenance from
  a known clean baseline, branched before any staging) and a
  pre-existing staged set, which is preserved exactly and never broadened. An empty index without
  eligible provenance — including `main` without a known clean
  baseline and task-owned scope — or a clean empty index with no
  work to ship, is a scope blocker (`staged_empty`). Unstaged
  tracked changes or untracked files alongside a non-empty index
  make the candidate unclean (`scope_unclean`); they are rejected
  before publish and are never swept into the candidate, hidden,
  stashed, or deleted.
- Scope is surfaced, not reconfirmed. Worker surfaces the staged
  files and outgoing commits from the helper decision and from
  `ship-build` output. In routine cases (non-empty staged scope,
  including a scope newly created by the single reviewed
  auto-staging, with no unclean files) Cal does not ask the user to
  reconfirm them. Cal stops and asks only on a real scope surprise
  (the staged set contradicts explicit prior instructions), a
  repository policy or authority limit, a failed gate, or a tool
  denial.
- `main` synchronization state. A local `main` that is ahead of or
  diverged from the current remote `main` blocks. A local `main` that
  is only behind may be fast-forwarded only when the fast-forward is
  safe and preserves the staged work; otherwise it blocks. The check
  runs on and off `main` against a freshly fetched remote `main`, with
  correct ahead and behind counts. A feature branch being ahead of its
  base is normal and is not by itself a block.
- Effective local readiness. Worker confirms `git status`, staged
  stat, and the branch list reflect the Step 2 decision. If any
  decision is ambiguous, consequential, or denied by permissions,
  return to the user before resuming.

## Step 3 - Run the ship-build script

Before invoking ship-build, Worker crafts a meaningful Conventional Commit
message from the staged scope and the repository's Commitlint policy
(for example `feat: add Companion config manager`) and passes it as
`--message`. The message must describe the staged change and use a
type the Commitlint policy accepts — never `ship:`, never a mechanical
topic slug or placeholder. Worker runs with the Step 2 helper values
(remote, ref, branch when on `main`), so no routine git-derived value is
demanded from the user. On the auto-staging
path these are the rerun helper values (the reviewed newly staged
set), not the first `staged_empty` output:

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
the single exact outgoing SHA, then runs check, deploy, run in that
order. When the candidate carries the isolated contract, the fleet
`scripts/ship/ship-e2e-runner` preflight runs first: it reads the
versioned digest-pinned OCI contract from the candidate commit,
verifies the runner image is already present locally with no
implicit pull, and records the image id and contract hash. Only
then does `ship-deploy` run `<repo>/scripts/ship-deploy <SHA>` for
the non-production rollout and verify the single deterministic
`SHIP_DEPLOYED_SHA` line naming that SHA. After rollout, the runner
re-verifies the same contract hash and the same image id and runs
the full owner `test:e2e` suite inside that exact image with
`SHIP_TARGET_SHA` and `SHIP_DEPLOYED_SHA` set to the candidate, with
no host Node or package manager and no host fallback. When the
candidate has no contract, the suite runs on the host in legacy
mode, recorded as `legacy_host` migration debt. The repository's
E2E suite must finish successfully. Every step succeeds before Git
uploads anything; any failure exits non-zero and blocks the push.
The shared layer does not classify tests and does not ask which
tests to run: the whole `test:e2e` suite runs every time. Receipt
content, not a filename, binds the run to the candidate, remote,
and ref. Worker never runs the runner directly and never falls
back to a host invocation when isolation is declared; a missing
image or a drifted image is a blocker, reported with its preflight
output preserved.

Deployment goes to the repository's existing configured non-production
target only: the repository's own `scripts/ship-deploy` entry. If that
repository configures a lease or reservation mechanism for its
non-production target, that mechanism runs inside the repository entry
itself and the fleet wrapper lets it run; the fleet layer invents no
global reservation system and holds no lock of its own. A deploy that
reports a busy lease or an unverifiable required reservation is a
specific blocker: `ship-deploy` preserves its output, the push is
blocked, and Cal reports that specific lease reason to the user. The
workflow never asks whether someone is using the target, never polls
for the lease to free up, never retries by an alternate deploy path,
and never proceeds without the rollout and the full E2E run. When the
repository configures no lease, no lease check is invented; the known
race limit in `docs/ship.md` still applies.

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
   owner and repository from the selected Step 2 destination, the base
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
order: be on a named topic branch with the change to ship (on `main`
staged work ships and unstaged task-owned work with a known clean
baseline and established task-owned provenance is reviewed and
auto-staged once in Step 2; off `main` unstaged work is reviewed and
auto-staged once in Step 2; in either case the Step 2 destination
helper resolves the topic on rerun, on `main` to a safe derived
topic with no publish or commit directly to `main`, no separate
ask); meet the strict standard so
`scripts/ship-doctor <repo>` reports `local_pass`; install the pinned
Husky v9 runtime and verify the helper, shims, and the single-line
pre-push delegation; add executable `scripts/ship-deploy` with the
one-SHA-argument and single `SHIP_DEPLOYED_SHA` line contract; wire
`.husky/pre-push` to the fleet `scripts/ship/ship-deploy` wrapper per
`docs/ship.md`; keep run evidence under `.git` (never commit it); and
run the realistic fixtures in `tests/ship_workflow_test.py` until a
real push of the exact candidate succeeds. To migrate from legacy to
isolation, add a valid `.ship/e2e-runner.json` with a digest-pinned
image that is present locally before rollout and runs the suite
inside that image, keep the isolated fixtures green, and only then
claim isolation; until then the repository stays legacy migration
debt and is never reported as isolated. Authorization stays with
Cal; Worker reports blockers rather than adapting around them.
