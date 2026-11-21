---
name: Ship
description: Ship a change through Husky gates, non-prod deploy, full E2E, and an open GitHub PR
metadata:
  opencode/autoinvoke: false
---

# Ship

Ship a change through Husky commit/push gates, non-production deploy, full E2E
tests, and an open GitHub pull request for review.

- **Requires a write-capable agent** (`build`, `frontend`, or `mark`). If invoked
  from a read-only agent (`cal` or `reviewer`), tell the user to switch to
  `build` and stop.
- **Strict opt-in only.** A repository must conform to the standard in
  `docs/ship.md`. Never adapt around missing requirements or modify a repository
  to become compatible without an explicit request from the user.
- **No gate bypasses.** Never use `--no-verify`, `HUSKY=0`, or alternate push
  paths. Production deployment and PR merging are out of scope.
- **Autonomous once ready.** Once Step 1 passes, run Steps 2–4 end-to-end
  without asking routine confirmation questions. Stop only on a real blocker and
  report the exact issue.

Locate the fleet scripts under the `the-team` checkout (`<the-team>/scripts/ship/`).

## Step 1 — Check compatibility (`ship-doctor`)

Run the read-only compatibility check against the target repository root:

```sh
<the-team>/scripts/ship/ship-doctor <repo-path>
```

- If it exits non-zero (`status: "not_ready"`), **stop immediately**. Report
  each item in `issues` along with its `fix` guidance so the user can decide
  whether and how to opt the repository in. Do not edit the repository.
- If it exits `0` (`status: "ready"`), proceed to Step 2.

## Step 2 — Review scope and choose names

Inspect the repository state (`git status`, staged and unstaged `git diff`,
untracked files, and `git log main..HEAD`):

1. **Coherence and safety.** Confirm the change is a single coherent piece of
   work with no secrets, credentials, or unintended scratch files. If the tree
   has mixed unrelated changes, likely secrets, or nothing to ship (clean tree
   and no commits ahead of `main`), stop and report the blocker.
2. **Determine commit inputs:**
   - **Clean topic branch ahead of `main`** (e.g. retrying after a failed deploy
     or E2E run): no new commit or staging is needed; skip `--stage` and
     `--message`.
   - **Uncommitted or staged changes:**
     - Choose the exact paths to stage (never gitignored files or secrets). If
       files are already staged and the tree is otherwise clean, omit `--stage`.
     - If currently on `main`, choose a short, descriptive topic branch name
       (e.g. `feat/config-manager`, `fix/e2e-timeout`) — never `main`.
     - Write a concise Conventional Commit message matching the repository's
       commitlint rules (never `ship:`).

## Step 3 — Run the ship pipeline (`scripts/ship/ship`)

Run the deterministic fleet script with the values from Step 2:

```sh
<the-team>/scripts/ship/ship <repo-path> \
  [--branch <topic>] \
  [--message "<conventional-commit>"] \
  [--remote <remote>] \
  [--stage <path> ...]
```

This script handles the entire repeatable procedure: re-runs `ship-doctor`,
activates a pinned Node version from `.nvmrc` / `.node-version` if present,
fast-forwards local `main` when behind-only (failing if ahead or diverged),
creates `<topic>` off `main` before staging, stages exact paths, commits via
plain `git commit` (running Husky `pre-commit` and `commit-msg`), pushes
`<sha>:refs/heads/<topic>` (triggering `.husky/pre-push` → `ship-deploy` →
repo `./scripts/ship-deploy <sha>` + full `test:e2e`), verifies the remote ref,
switches back to `main`, and prints `SHIP_RESULT_JSON=...`.

- If `ship` fails (hook, commitlint, deploy, E2E, lease/reservation, or git
  state), stop and return the exact failure output to the user. Do not retry
  blindly or work around the failure.

## Step 4 — Open or reuse the GitHub PR

Parse `owner`, `name`, `branch`, `base`, `sha`, and `commits` from
`SHIP_RESULT_JSON`:

1. Check for a repository PR template (`.github/pull_request_template.md`,
   `.github/PULL_REQUEST_TEMPLATE/`, or `docs/pull_request_template.md`). If
   none exists, use `<the-team>/fleet/skills/ship/resources/PR_TEMPLATE.md`.
2. Using GitHub MCP, list open pull requests for `owner`/`name` matching
   `head=<owner>:<branch>` and `base=<base>`.
   - If one open PR matches, reuse it (and update its body if helpful).
   - If none matches, create one with a clear title and concise summary of what
     changed, the verified candidate `sha`, and the gates/E2E that passed.
3. Verify the PR is open and its head SHA equals `sha`, then report the PR URL
   and summary to the user. Never merge the PR.
