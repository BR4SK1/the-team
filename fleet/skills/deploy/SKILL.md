---
name: Deploy
description: Deploy tested code to a repository's production environment using its standardized root-level scripts/deploy entry point.
---

# Production deployment workflow

Use this skill only when the user explicitly authorizes deployment of tested code
to a specified repository's production environment. Loading this skill,
discussion, preparation, or tool-access approval alone is not authorization. The
request authorizes deployment only within its stated scope; it does not override
the active agent's role, tool permissions, repository instructions, or access
controls.

## Establish the target and readiness

1. Identify the intended repository root and production target from the user's
   request and that repository's instructions. If either is materially ambiguous,
   ask the user before proceeding; do not guess a target.
2. Confirm which relevant checks passed for the exact code being deployed. If the
   test status is unknown, failed, stale, or does not cover the current changes,
   ask the user before proceeding when that uncertainty is material. Do not call
   unverified code tested.
3. Inspect the repository-root `scripts/deploy` entry point and its stated target
   before requesting deployment. It must exist and be executable. If it is
   missing, non-executable, inaccessible, or denied by permissions, stop and
   report that deployment did not happen. Do not guess or substitute another
   command, path, wrapper, elevated access, or `scripts/deploy.sh`.

## Delegate execution to Worker

The primary agent must delegate the deployment to the Worker subagent; the
primary agent must not run `./scripts/deploy` directly. Give Worker the verified
repository root, production target, code/version and relevant test evidence, and
the scope of the user's explicit authorization. Worker runs only the standardized
entry point described below and returns its actual stdout, stderr, exit status,
and any blocker to the primary agent. If Worker is unavailable, cannot run it,
or encounters denied access, stop and report that deployment did not happen;
there is no direct-run fallback, permission bypass, or alternate deployment
mechanism.

Follow fleet instructions for delegation. Cal may invoke Worker in the
background where supported, but do not claim durable execution, monitoring, or
completion until Worker has actually returned its result. Worker is a leaf and
does not further delegate.

## Run and report

Worker must run only the repository's standardized root-level entry point, from
the verified repository root:

```sh
./scripts/deploy
```

Do not run it when permission is denied or required approval has not been
provided. Do not bypass a denial or repeat the operation through another
mechanism. Worker must capture and return the command's actual stdout, stderr,
and exit status, including empty streams, and report any blocker. Treat any
nonzero status or output identifying the operation as a placeholder, dry run,
skipped, or otherwise not actually deployed as **not deployed**, even if the
status is zero. Do not infer deployment success from a message or a zero status
alone when the output indicates otherwise.

The primary agent reports the target, relevant test evidence, exact command,
Worker's actual stdout and stderr, exit status, blockers, and outcome. Redact secrets
and other sensitive values from output; never expose credentials, tokens, private
keys, or sensitive environment data. Distinguish a deployment attempt
from a successful deployment, and state plainly when deployment did not happen
or success could not be verified.
