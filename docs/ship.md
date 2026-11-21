# Ship workflow

`@ship` ships a change through Husky commit and push gates, a non-production
deployment, the repository's full E2E suite, and an open GitHub pull request
for review.

The workflow splits responsibilities cleanly:

- **Agent (LLM judgment):** checks compatibility, reviews the diff for
  coherence and safety, chooses a topic branch name and Conventional Commit
  message, and writes the pull request.
- **Scripts (`scripts/ship/`):** execute the repeatable Git, Husky, Node
  version, deploy, E2E, and push mechanics deterministically.

## Strict opt-in standard

Shipping is strictly opt-in. Running `@ship` always starts with `ship-doctor`:
if a repository does not conform, `@ship` reports what is missing and how to
configure it, then stops. Making a repository compatible is an intentional user
decision, never done automatically by an agent.

A conforming repository has:

| Requirement | Expected shape |
| --- | --- |
| Git repo | Repository root with a local `main` branch and at least one GitHub remote |
| Package manager | Root `package.json` with pinned `packageManager` (`npm\|pnpm\|yarn\|bun@x.y.z`) and matching non-empty lockfile |
| Node pin *(optional)* | Root `.nvmrc` or `.node-version` naming an installed Node.js version (e.g. `22.23.4`) |
| Required scripts | `package.json` scripts: `prepare: "husky"`, `format:check`, `lint`, `test:unit`, `test:e2e` |
| Husky v9 | `husky` in `dependencies`/`devDependencies`, `git config core.hooksPath` = `.husky/_`, `.husky/_/h`, user hooks `.husky/pre-commit`, `.husky/commit-msg`, `.husky/pre-push`, and executable `.husky/_/` shims |
| Pre-push wiring | `.husky/pre-push` has one effective line: `exec "<the-team>/scripts/ship/ship-deploy"` |
| No gate bypasses | No `--no-verify` or `HUSKY=0` in `.husky/` hooks |
| Non-prod deploy | Executable `scripts/ship-deploy` at the repo root that takes `<40-hex-SHA>`, deploys it to non-production, and prints `SHIP_DEPLOYED_SHA=<SHA>` on stdout |

## Components

All ship scripts live together under `scripts/ship/`:

- `scripts/ship/ship-doctor <repo>` — Read-only compatibility checker. Prints
  JSON (`status: "ready" | "not_ready"`, `checks`, and actionable
  `issues[].fix` instructions). Exit `0` when ready, `1` when not ready, `2` on
  invalid arguments.
- `scripts/ship/ship <repo> [options]` — Deterministic end-to-end git/gate/push
  pipeline:
  1. Re-runs `ship-doctor` (fails immediately if not ready).
  2. Activates the repo's pinned Node.js version from `.nvmrc` or `.node-version`
     if present.
  3. Resolves the GitHub remote and guards against `pushurl`, `mirror`, and
     `tagOpt=--tags`.
  4. Fetches `<remote> main` and fast-forwards local `main` when behind-only
     (fails if local `main` is ahead or diverged, or if fast-forwarding would
     collide with local edits).
  5. Creates `<topic>` off `main` before any staging or commit (never stages or
     commits on `main`).
  6. Stages exact `--stage` paths (rejecting gitignored paths and any leftover
     unstaged/untracked files) and runs plain `git commit -m <message>` so
     Husky `pre-commit` and `commit-msg` gates run. If already clean on a topic
     branch ahead of `main` (for example, retrying after a failed deploy/E2E),
     skips committing and pushes `HEAD`.
  7. Pushes `<sha>:refs/heads/<topic>`, which triggers `.husky/pre-push` →
     `scripts/ship/ship-deploy`.
  8. Verifies the remote ref via `git ls-remote`, switches back to `main`
     (leaving the topic branch intact), and prints `SHIP_RESULT_JSON=...` for
     PR creation.
- `scripts/ship/ship-deploy` — Fleet pre-push wrapper invoked by the target
  repository's `.husky/pre-push` hook:
  1. Parses the single outgoing branch ref from Git's pre-push stdin and checks
     that `HEAD`, current branch, and a clean working tree match the outgoing
     SHA.
  2. Activates the repo's pinned Node.js version (`.nvmrc` / `.node-version`)
     if present.
  3. Runs `./scripts/ship-deploy <SHA>` and requires exactly one
     `SHIP_DEPLOYED_SHA=<SHA>` line matching the candidate.
  4. Runs `<packageManager> run test:e2e` with `SHIP_TARGET_SHA=<SHA>` and
     `SHIP_DEPLOYED_SHA=<SHA>` in the environment.
  5. Re-checks that `HEAD` and the working tree did not drift, then exits `0`
     to allow the push (any failure exits non-zero and blocks the push).
- `scripts/ship/_node-env.sh` — Shared helper sourced by `ship` and
  `ship-deploy` to prepend a matching installed Node.js `bin/` directory to
  `PATH` when `.nvmrc` or `.node-version` is present (checks `NVM_DIR`, `fnm`,
  `mise`, and `volta`). Fails clearly if the pinned version is not installed.
- `scripts/ship/check` — Local check runner for `the-team` itself (also wired
  via `.githooks/pre-commit`).

The skill lives at `fleet/skills/ship/SKILL.md` (`opencode/autoinvoke: false`),
with a fallback PR template at `fleet/skills/ship/resources/PR_TEMPLATE.md`.

## Onboarding a repository

To opt a repository into `@ship`:

1. Run `<the-team>/scripts/ship/ship-doctor <repo>` to see the checklist of
   missing items.
2. Add `packageManager`, lockfile, required scripts, and optional root `.nvmrc`
   (if the repo requires a specific Node version that differs from the OS
   default on `PATH`).
3. Install Husky v9 (`prepare: "husky"`), configure `.husky/pre-commit` and
   `.husky/commit-msg`, and point `.husky/pre-push` at the fleet wrapper:
   ```sh
   #!/bin/sh
   exec "<the-team>/scripts/ship/ship-deploy"
   ```
4. Add an executable `scripts/ship-deploy` that deploys `<40-hex-SHA>` to
   non-production and prints `SHIP_DEPLOYED_SHA=<SHA>`. If the repository uses
   a deployment lease or reservation, implement it inside `scripts/ship-deploy`
   so a busy lease blocks the push with a clear error message.
5. Re-run `ship-doctor <repo>` until it reports `ready`.

## Boundaries

- **Husky is the only gate.** Neither the skill nor the scripts ever pass
  `--no-verify` or `HUSKY=0`.
- **No production deploys or automatic merges.** `@ship` deploys only to the
  repository's non-production target and opens a PR for human review.
- **No per-repo adapters.** Shared scripts stay generic; repository-specific
  deploy or test behavior lives inside the repository's own
  `scripts/ship-deploy` and `package.json` scripts.

## Verification

Run `./scripts/ship/check` in `the-team` to verify shell syntax (`shellcheck`
and `bash -n`), Python syntax, unit tests (`tests/ship_doctor_test.py` and
`tests/ship_test.py`), fleet JSON/JSONC validity, agent/skill frontmatter,
private-path leaks, and `.gitignore` rules.
