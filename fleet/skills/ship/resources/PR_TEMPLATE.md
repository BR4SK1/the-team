## Summary

<!-- What changed and why. -->

## Changes

- Commits:
- Candidate SHA:

## Verification

- `ship-doctor`: `ready`
- Husky commit gates (`pre-commit`, `commit-msg`): passed
- Non-production deploy (`scripts/ship-deploy <SHA>`): `SHIP_DEPLOYED_SHA=<SHA>`
- Full `test:e2e` against deployed SHA: passed

## Risks and follow-up

- Rollback or follow-up notes:
