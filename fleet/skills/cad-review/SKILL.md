---
name: CAD Review
description: Use for review-only CAD and mechanical-model assessment — construction quality, evidence, provenance, and verification claims. Required for CAD review by Reviewer. Review-only; never implements, builds, exports, or operates live CAD.
---

# CAD review workflow

A review-only companion to the modular CAD workflow. Use it when reviewing a
CAD or mechanical-model change, its construction, or its verification claims.
Review what was built and claimed; do not implement, build, export, or repair
anything. This skill does not grant tool permissions or authorize changes.

## 1. Separate safe inspection from out-of-scope execution

- **Safe read-only inspection** (review scope): reading source files, project
  instructions, generated artifacts, manifests, build logs, and check reports;
  the exact hardened Git inspection invocations permitted by the agent
  definition (`git --no-optional-locks -c core.fsmonitor=false status`,
  `git --no-pager diff/log --no-ext-diff --no-textconv` forms); textual
  inspection of STEP files and similar formats where informative. These exact
  forms disable the known command-execution paths git consults for inspection
  (configured external diff, textconv, and pager helpers, optional locks, and
  the fsmonitor hook), which wildcard shell rules would otherwise permit.
- **Out of review scope**: builds, exports, tests, geometric recomputation, or
  any script that writes files, regenerates geometry, or operates a live CAD
  application. These belong to Mark or Worker under user authorization. The
  reviewer's permissions should exclude them; if a review cannot proceed
  without an executed check, state the limit instead of working around it.
- These exact forms constrain the allowlist; they are not a complete security
  sandbox. Git still honors other configuration, and the permission match is
  on the exact command text only.
- Do not control or save over a live CAD session, and do not propose
  destructive or difficult-to-reverse inspection of owner work.

## 2. Assess construction quality

Apply the governing rule of the shared CAD workflow: one authoritative
editable construction model, features independently understandable and
removable, and source-level changes rather than repair layers.

- One active master: is there a single authoritative construction source, and
  does the documented build command target it? Are competing or commented-out
  copies of whole models accumulating?
- Modular features: are features named, parameterized, and removable without
  collateral changes? Are shared interfaces derived from one parameter source?
- Repair chains: do later operations compensate for unwanted results left
  active upstream (counteracting cuts, unions, fills, masks, or face edits)?
  A clearly disabled or commented-out feature call is acceptable; a
  compensating patch on obsolete code or geometry is not.
- Reference integrity: are owner documents and vendor originals preserved?
  Note silently healed, rescaled, moved, or replaced reference hardware.

## 3. Assess evidence and provenance

- Trace each claimed change to the source revision and the artifacts it
  produced. Distinguish editable masters, references, generated artifacts, and
  protected owner work; do not treat the latest-named file or a prior agent's
  report as authoritative without checking.
- Agent-authored revision notes are evidence, not proof of owner approval or
  physical measurement. A stale manifest does not describe later owner edits.
- STEP/BREP artifacts carry geometry, not the editable feature tree; do not
  accept claims that a baked-in feature was removed by tree cleanup or mesh
  repair.

## 4. Assess verification claims

- For each reported check, determine what it actually verified: which inputs,
  poses, solids, and regions; whether sections, before/after differences, or
  installed-reference checks were used, or only bounds, volume totals, or a
  passing label.
- Unchanged bounds or net volume alone are not proof of a correct change.
  Collision filtering must include containment; imported compounds may need
  valid individual solids.
- Nominal CAD checks never establish fit, strength, serviceability, cooling,
  or print readiness. Distinguish source review, valid solids, verified
  geometric relationships, and physical qualification.

## 5. Report

- Lead with findings ordered by severity. For each finding give severity,
  concrete file/line or artifact evidence, impact, and a practical correction
  described as a recommendation, not an implementation.
- Separate defects from preferences, and confirmed observations from
  assumptions and physical uncertainty.
- State verification limits explicitly: which checks were not run, which
  artifacts were not inspected, and who is authorized to run the missing
  checks (Mark or Worker, with user approval).
- If there are no findings, say so explicitly.
