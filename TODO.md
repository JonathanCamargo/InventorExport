# TODO — glTF/GLB Export: Debugging Session Notes

_Last updated: 2026-08-29. Read this before resuming work on the glTF writer._

## Current Status: exports work, bone/joint LOCATIONS look wrong

The last user report after re-exporting the palletizer (`--format glb -v`):

> "number of joints is good but locations are weird"

- Bone/joint COUNT and hierarchy are now correct (6 links, 5 joint edges
  for their 5-axis palletizer).
- **Positions/orientations of bones and/or geometry are wrong in the
  viewer.** This is the open bug. Debugging had just started when this
  document was written — no fix has been applied yet for this issue.

---

## Session context (everything done so far)

### 1. Shipped and working

These are complete and validated; don't re-litigate them:

- **glTF/GLB writer** (`src/inventor_exporter/writers/gltf.py`), registered
  as both `gltf` and `glb`, output variant chosen by file extension.
- **Web default tolerance 0.5mm** (`mesh_tolerance`), angular tolerance
  ramped alongside (`max(0.1, min(0.6, 0.3 * tolerance/0.5))`) — rounded
  parts are angle-dominated.
- **cadquery tolerance bug fixed** in `mesh_converter.py`:
  `cq.Shape.exportStl` silently ignores deflection (positional
  `BRepMesh_IncrementalMesh` ctor). Now uses `IMeshTools_Parameters`
  directly + `BRepTools.Clean_s`. Mesh sizes dropped ~8x at 0.5mm.
- **Skin/armature**: one bone per rigid body, `JOINTS_0`/`WEIGHTS_0`
  (UNSIGNED_SHORT, skin-relative indices, unused slots zeroed), world-space
  vertices, column-major flattened IBMs from GLOBAL bind pose (incl. Y-up
  root), `skin.skeleton` = the bone with no bone-parent. Passes the Khronos
  glTF validator with **0 errors** (NODE_SKINNED_MESH_* warnings are
  standard for skeletal hierarchies, same as Blender exports).
- **Stale mesh cache caveat**: `MeshConverter` skips existing STLs — delete
  `meshes/` after changing tolerance (documented in README; note the repo
  root has a stray `meshes/` dir right now, untracked).
- CLI warning when an assembly exports with bodies but zero constraints.
- Constraint metadata goes to top-level `extras: {constraints: [...]}`.
- `load_stl()` helper parses binary+ASCII STL for embedding.

### 2. The subassembly joint-resolution bug (FIXED, this session's main win)

**Symptom**: user's 5-axis palletizer exported 19 flat bones, 0 joint→joint
links. Reviewer confirmed: "geometry-with-transforms rather than a
kinematic chain."

**Root cause** (proven from the user's verbose log): Inventor joints
reference **subassembly occurrences** (`Link1:1`, `base:1`) but the
exporter built bodies from **leaf parts only** (`1_30_00268_391`, ...).
`classify_joints` matched joint occurrence names against leaf body names →
zero matches → all joints silently dropped.

**Fix implemented** (all pieces must stay in sync):

| File | Change |
|---|---|
| `extraction/assembly.py` | `_recurse_occurrences` now passes `ancestors` (sanitized subassembly names, root-first) into `OccurrenceData` |
| `model/body.py` | New `ancestors: tuple[str, ...]` field, sanitized in `__post_init__` |
| `extraction/client.py` | `_build_body` passes `occ.ancestors` through |
| `model/assembly.py` | `occurrence_aliases()` maps alias → [leaf body names]; `rigid_groups(occurrence_aliases=)` fuses leaf bodies under any **constraint-referenced** subassembly into one rigid unit, group renamed to the alias |
| `model/kinematic_tree.py` | `classify_joints(occurrence_aliases=)` resolves joint occurrence names via aliases → group rep; alias reps added to the graph node set (`body_set |= {reps}`) |
| All writers + CLI | Compute `aliases = model.occurrence_aliases()`, pass to both `rigid_groups()` and `classify_joints()` |
| `writers/gltf.py` | Group emission: member meshes as children of group node sharing one bone; root selection iterates **group reps** not bodies; `_resolve_to_body()` maps child rep names (alias or member) to a member body; member child indices merged with tree child indices (was: overwrite bug) |

**Test replica of the palletizer** (verified working, Khronos 0 errors):
leaf parts in subassemblies `base:1` (2 parts), `Link1:1` (2), `Link2:1`
(2), `Link3:1` (2), `Link4:1` (1), `Link5:1` (1); joints
`Rotational:1..5` referencing those subassembly names. Result: 6 bones,
5 joint→joint edges, BFS rooted at Link2 (most-connected).

Regression test: `tests/writers/test_gltf.py::TestSkeleton::test_subassembly_joints_resolve_to_leaf_bodies`.

### 3. OPEN BUG — "locations are weird" (ACTIVE)

First analysis, started right before this doc (nothing committed):

Relevant code path in `writers/gltf.py::_add_body_node` (around line 418):

```python
if group_members:
    node["name"] = "_".join(group_members[:2]) + "_group"
    ...
    for member_name in group_members:
        member_rel = member.transform.relative_to(body.transform)   # <-- SUSPECT
```

**Hypothesis A (most likely)**: fused-group node transforms are built
relative to `body` — the *first body the writer happened to process from
that group* — but the group's tree edges/parent transforms come from the
BFS parent chain, and the group's global matrix (`_skin_global`) is
accumulated through `parent_global @ local` where `local` is the repr body's
world transform relative to + its PARENT's world transform. For fused
subassembly groups this mixes frames: a group's node should be placed at
the **subassembly's own frame** (or a consistent reference), but each
member's `relative_to(body)` uses an arbitrary first-processed body. When
two members have different orientations, `relative_to` bakes the first
member's rotation into every other member's local transform — and the
group node itself sits at the first member's pose, not the subtree root's.

**Why this now breaks**: the nodes are ALIAS-fused groups whose members
come from world-positioned leaf transforms; the previous (pre-alias)
structure never had groups spanning subassemblies.

**Where to look next**:
1. `_resolve_to_body()` returns `mem[0]` for alias children — the group
   node's *pose* then comes from `members[0]`'s world transform (line ~530
   `_add_body_node(child_body, body, ...)`): that means the chosen
   representative depends on **body insertion order**, not on the joint.
   If the joint pivot belongs to a different member, the chain pivots at
   the wrong point → "locations are weird".
2. Joint origins (`ConstraintInfo.origin`, in `extras`) are NOT being used
   to position bones. Bones sit at member part origins instead of at joint
   locations. For a palletizer, users expect bones to be AT the joint
   pivots (the shoulder/elbow lines in a SkeletonHelper). Right now bone =
   part origin, which can be meters away from the actual revolute axis —
   possibly the whole complaint.
3. `_skin_global` accumulation for group nodes uses `global_matrix` of the
   repr body; if the repr is in a different world pose than the subassembly
   frame, IBM/bind math stays consistent (world-space vertices) but the
   *visual* bone placement is off.

**Candidate fixes (discuss/decide before coding)**:
- Option 1 (minimal): keep bone-at-part-origin but verify members' world
  positions visually match; if the only complaint is bone lines in odd
  places, the fix is cosmetic: add a dedicated joint-origin node between
  parent and child (`node_j1` at `ConstraintInfo.origin` world position,
  acting as pivot) so rotation happens about the real axis.
- Option 2 (proper): build the skin chain from the **kinematic tree
  edges**: each tree edge (parent rep → child rep via joint) inserts a
  pivot node at the joint's world origin; bones = bodies between pivots.
  Requires passing `ktree.joint_for` origin/axis into node construction.
- Option 3: if the complaint is geometry misplaced (not just bones), then
  the bug is in `_transform_mesh_to_world` / `relative_to` math for fused
  members — write a test with TWO members in one group at different world
  poses and assert their GLB bounds land in the right world spots.

**Test-first suggestion**: extend the palletizer mock in
`test_gltf.py::TestSkeleton` with geometry + asymmetric member transforms,
then assert (a) ACCESSOR min/max world bounds per mesh, (b) node
translations equal `body.transform.relative_to(parent)` expected values.
Whichever assertion fails names the broken math.

### 4. Known quirks (not bugs; leave as-is unless asked)

- `NODE_SKINNED_MESH_NON_ROOT` / `NODE_SKINNED_MESH_LOCAL_TRANSFORMS`
  validator warnings (severity 1, informational): standard for skin hierarchies.
- `NON_OBJECT_EXTRAS` fixed by wrapping extras (`{constraints: [...]}`).
- World-space vertex data means `meshes/` STL cache reuse is safe, but old
  (pre-fix) STLs must be deleted after tolerance changes.
- The BFS root is the **most-connected** body (or ground if matched); for
  the palletizer mock this landed on Link2, so the "armature skeleton
  root" is mid-chain. Cosmetic; a root at the actual base would be nicer.
  `ground_body` is currently never set by extraction (defaults to
  `"ground"`, never matches) — wiring real ground detection would move
  BFS root to the grounded link.

### 5. Test & validation loop

```powershell
# Unit tests (extraction tests have 2 pre-existing failures unrelated to
# this work: CM3_TO_M3 import error + 4 in test_extraction_assembly.py)
python -m pytest tests -q --ignore=tests/test_extraction_properties.py `
  --ignore=tests/test_extraction_assembly.py

# Khronos validator (node available; package installed in
#   C:\Users\jcl00\AppData\Local\Temp\opencode)
cd C:\Users\jcl00\AppData\Local\Temp\opencode
node -e "const v = require('gltf-validator'); const fs = require('fs');
v.validateBytes(new Uint8Array(fs.readFileSync('FILE.glb')), {maxIssues: 12})
 .then(r => console.log('errors:', r.issues.numErrors, 'warnings:', r.issues.numWarnings))"
```

Reusable test fixtures in the temp dir (may be cleaned by OS, recreate if
missing): `palletizer_check.py`, `pal_geom.py` (palletizer sim with
geometry), `trace_tree.py`, `dump_nodes.py`, `final_tree.py`.

### 6. User's context (why this matters)

- Goal: palletizer (5 rotatable axes) → web viewer (three.js) with working
  skeleton articulation; rig came through in the latest export.
- Web delivery: 0.5mm tolerance + optional `gltfpack -cc -si 0.5`.
- A 32MB GLB mystery earlier was the stale `meshes/` cache — solved.
- User validates with an external reviewer tool: decodes JOINTS_0/WEIGHTS_0,
  counts joint→joint links. Final acceptance test: rotate a bone in the
  viewer and watch the whole sub-tree move (mechanism-style).

## Ground rules established this session

1. glTF has no mechanical joints; skin+bones is the DCC-recognized
   armature. Bone = rigid body (fused parts), hierarchy edge = kinematic
   joint. Rigid joints NEVER get bones of their own.
2. Always validate with the Khronos validator before claiming anything.
3. Never claim "100% sure" without running the user's exact scenario —
   the subassembly bug survived three rounds of confident but incomplete
   testing because mocks used body names instead of subassembly names.