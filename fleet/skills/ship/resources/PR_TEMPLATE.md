<!-- Copy this template into the PR body when creating or reusing an open PR. -->
## Summary

<!-- What changed and why. Keep the repository's own summary here. -->

## Staged scope (reviewed)

- Staged files:
- Outgoing commits:

## Evidence (exact candidate SHA)

- Candidate SHA:
- Doctor: `local_pass` (exit `0`)
- Run evidence: `.git/ship-runs/<run-id>/commit.json` and `deploy.json`
  (content-bound to run, candidate SHA, remote, and ref)
- Deploy: `scripts/ship-deploy <SHA>` printing exactly one deterministic
  `SHIP_DEPLOYED_SHA=<SHA>` line, plus full `test:e2e` run with
  `SHIP_TARGET_SHA=<SHA>` and `SHIP_DEPLOYED_SHA=<SHA>` in the environment
  against that SHA
- Remote ref verified: `git ls-remote <remote> <ref>` = candidate SHA
- PR head verified: the PR object's head SHA equals the candidate SHA

## Tests

- `test:e2e`: the repository's E2E suite must finish successfully
  against the non-production deployment of the exact candidate SHA.
- Other gates (Husky commit hooks): list the repository's actual
  results here; do not claim an unrun gate passed.

## Risks and follow-up

- Non-production deployment of the exact candidate SHA:
- Rollback or follow-up owner:
