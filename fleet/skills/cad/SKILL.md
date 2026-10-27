---
name: CAD
description: Use for CAD and mechanical-model investigation, planning, implementation, or review, especially modular feature changes, geometry removal, parametric source models, assemblies, and FreeCAD/build123d/STEP verification. Required for CAD work by CAD and Worker.
---

# Modular CAD workflow

## Governing rule: change the construction, do not patch the patch

Maintain one authoritative editable construction model for each active design.
Build it from declared parameters, named features, and approved reference
geometry. Generated enclosure exports are review artifacts, not the construction
foundation of the next revision. Third-party reference geometry is different:
it can be a declared input with explicit identity, pose, purpose, and limits.

**Do not stack repair code on obsolete code or repair geometry on previously
patched geometry.** Fix or remove the operation that created the unwanted
feature, then regenerate from source. Do not add compensating cuts, unions,
fills, masks, or face edits merely to hide its effect. If the source cannot
express the requested change cleanly, stop and explain the required source-model
refactor or reconstruction rather than extending the repair chain.

Disabling or commenting out a coherent feature call is acceptable, and better
than counteracting it later. Prefer an explicit feature flag or variant when a
feature is routinely toggled. Label temporary omissions and why they are off;
do not claim commented-out geometry is present. Git preserves permanent removal
history, so do not accumulate competing, commented-out copies of whole models.

This does not prohibit normal Boolean modeling, layered construction, code
refactoring, bug fixes, or diagnostic error handling. The distinction is whether
an operation expresses an intended feature of a clean construction model or
compensates for an unwanted result left active upstream.

## 1. Establish intent and authority

- Read the project's instructions and inspect the real modeling stack, version,
  source entry point, build path, assembly structure, and available checks.
- Identify which files are editable masters, references, generated artifacts,
  and protected owner work. Do not assume the latest-named file or a prior
  agent's "passing" report is authoritative.
- Distinguish final design removal, temporary simplification for recovery, and
  replacement of a feature's implementation while retaining its purpose. Ask
  only when that distinction materially affects the result.
- Separate owner statements and measured evidence from vendor estimates,
  agent-derived dimensions, inferred intent, and historical revision notes.
- State the requested change, the geometry to preserve, and the unresolved
  decisions. Do not broaden a repair into an unrequested mechanical redesign.

## 2. Make features independently understandable and removable

- Use named functions/modules with explicit parameters, inputs, outputs, and
  coordinate frames. Keep the top-level construction sequence readable.
- Keep base shells, optional mounts, channels, vents, and interfaces identifiable
  instead of scattering corrections to the same feature throughout the model.
- Treat a feature as a coherent unit: additive support, subtractive clearance,
  holes, fastener references, access envelopes, metadata, and checks. Disable or
  remove its dependencies together; identify intentionally retained shared
  supports instead of deleting them indiscriminately.
- Derive shared interfaces from one parameter source. Keep dependency direction
  clear; do not fix mismatched interfaces by patching both finished parts.
- Keep reference hardware, clearance tools, and manufactured parts distinct.
  A reference belongs in a shell Boolean only when that use is explicit design
  intent, not because it happens to be available as a solid.

Conceptual structure:

```python
body = make_base_shell(parameters)
body = add_keyboard_seat(body, interfaces)
if features.bottom_mounts:
    body = add_bottom_mounts(body, interfaces)
if features.cable_channel:
    body = cut_cable_channel(body, interfaces)
```

Removing `cable_channel` means disabling its construction call and related
outputs, not importing yesterday's body and unioning the channel cutter into it.
Removing a boss means omitting its addition, not subtracting its whole envelope
from walls or ledges that share that volume.

**A subtractive feature cannot generally be undone by adding its cutter back.**
The cutter may cross hollow interiors and unrelated clearances. Turning the
whole tool into material can create internal rods, shelves, blocked reliefs,
and protrusions. Rebuild the intended uncut construction instead.

For legacy artifact-only work, report the missing construction source and
propose a bounded recovery before implementation. A user-approved direct solid
edit is an explicit exception, not permission to grow a hidden patch pipeline
or call the result a reconstructed parametric model.

## 3. Use tools for their declared roles

- Follow the project's chosen authoring and inspection workflow. For a
  build123d/Python master, change Python; use FreeCAD for native inspection and
  assembly review, and STEP for interchange. A native FreeCAD parametric master
  is also valid when that is the project's actual source of truth.
- STEP/BREP import preserves geometry, not the original editable feature tree.
  Do not promise that refinement or deleting a tree item can remove a feature
  already baked into an imported solid. Mesh cleanup is not solid-model repair.
- Keep generation headless where possible. Imports must not start an editor or
  viewer. Use an isolated application process for export/reopen checks; do not
  control or save over the owner's live CAD session without explicit authority.
- Preserve owner documents and vendor originals. Use fresh output directories
  and record the input revision/configuration used. Do not silently heal,
  rescale, move, or replace reference hardware to make a fit check pass.
- CAD remains read-only; Worker writes code, runs builds, creates inspection
  evidence, and exports. A skill does not grant additional tool permissions.
  Read-only diagnostics must actually avoid writes, including import side
  effects. If inspection cannot be performed safely, state the limit.

## 4. Verify the intended change and its boundaries

Use checks that could expose a wrong construction, not just restate its recipe:

1. **Source structure:** one active master; the old operation and its dependent
   outputs are disabled/removed, not followed by a compensating repair. The
   documented build command targets that master.
2. **Geometric meaning:** test the removed feature's absence and the continued
   presence of required walls, ledges, and clearances. Inspect before/after
   sections or geometry differences; identify unexpected changes outside the
   feature's intended region. Unchanged bounds or net volume alone are not proof.
3. **Transforms and inputs:** inspect actual installed poses, units, transforms,
   and reference identities. Do not check an unplaced extraction against an
   assembled part. Preserve source shape locations when composing transforms.
4. **Topology and collisions:** check validity and intended solid counts; inspect
   internal/external remnants, overlaps, and assembly membership. Broad-phase
   collision filtering must include containment. Use valid individual solids
   when an imported compound is unsuitable. Evaluate alternatives separately.
5. **Assembly behavior:** where relevant, check mating parts, motion, removal,
   fasteners, access, and cable envelopes. Name sampled poses and unmodeled
   paths; do not imply continuous sweep or physical installation validation.
6. **Delivery:** verify exports and native reopen against the intended source
   geometry and placements. Record which artifacts were checked. A stale
   manifest does not describe later owner edits.

For a removable feature, disabling it, building, and restoring it should produce
the expected variants without unrelated changes or new repair operations.
Choose independent observations such as sections, installed-reference checks,
and preserved interface checks; a second agent accepting the same erroneous
assumption does not make a check independent.

## 5. Stop conditions and handoff

If repeated local corrections are necessary, reassess the construction model.
Do not weaken assertions, bless unexpected overlaps as intentional, substitute
another reference pose, or promote a troubleshooting omission to a design
decision just to release another revision. Bring consequential decisions to Cal
or the user; Worker owns routine corrections within the agreed scope.

Return a concise account of the intended result, affected features, preserved
geometry, checks actually performed, artifacts available for inspection, and
open decisions. Distinguish source review, valid solids, verified geometric
relationships, and physical qualification. Never call nominal CAD checks proof
of fit, strength, serviceability, cooling, or print readiness.
