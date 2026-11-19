---
description: Report ship-readiness diagnostics for a repository (shipping is not implemented yet)
---

Prompt-only command. Shipping is not implemented yet.

This command performs diagnostics only. It never ships, deploys, stages,
commits, pushes, installs, or otherwise mutates any repository, and it
never runs code from the target repository.

Diagnostics run only if execution is permitted for the current agent,
and the user has authorized diagnostics for an explicit repository
path. In that case, execute only the trusted, absolute, verified fleet
installation of the doctor: the fleet-managed script file at its
absolute fleet-checkout location, verified before execution to be that
fleet file and not a file from the target repository. Execution is
through the permitted executor only. Never execute a repository-relative
doctor path from the target repository or from the current directory,
and never treat target-repository code as trusted.

If execution is not permitted, is denied, or the trusted doctor cannot
be verified, report the diagnostics as not run and stop. Do not bypass
a denial, do not repeat the operation through another mechanism, and
do not substitute another command.

This command contains no OpenCode shell interpolation marker and no
other interpolation: it is prompt text only. Report the doctor's
versioned JSON result by its stable check IDs and reasons,
distinguishing a local pass from a blocked result and from an
indeterminate result, and state what the doctor did not check. Redact
secrets and sensitive values from any report; never expose file
contents, config or remote strings, credentials, or tokens. A
diagnostic result is local structural validation only: it is not
evidence that any test suite, hook, runtime, deployment, or
Web/native dispatch actually ran, passed, or is ready.
