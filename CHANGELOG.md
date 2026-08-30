# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Fixed: joints referencing subassemblies now build the kinematic chain

Real Inventor assemblies attach joints to **subassembly occurrences**
(`Link1:1`), not to individual parts — but the exporter built bodies from
leaf parts only (`1_30_00268_391`), so joint references matched nothing and
every assembly exported as a flat skeleton (one bone per part, zero
hierarchy). A 5-axis palletizer exported as 19 disconnected bones instead
of a 6-link / 5-joint armature.

- **Extraction** now records each leaf occurrence's ancestor subassembly
  names (`Body.ancestors`).
- **`AssemblyModel.occurrence_aliases()`** maps subassembly names to their
  leaf bodies; `rigid_groups()` fuses leaf bodies beneath a
  constraint-referenced subassembly into one rigid link (matching Inventor
  semantics: a joint on a subassembly moves its contents as one body).
- **`classify_joints()`** resolves constraint occurrence names through the
  aliases, so joints between subassemblies create real hierarchy edges.
- All writers (glTF, URDF, SDF, MuJoCo) and the CLI use alias-aware tree
  construction. The glTF writer also fixes internal node-linking bugs this
  uncovered (member meshes overwriting tree children; group nodes dropped
  from the scene root).
- Regression test reproduces the palletizer topology: joints naming
  `Link1:1`/`base:1` over leaf-part bodies produce correct bone→bone
  hierarchy.

### New: glTF 2.0 / GLB export (`--format gltf` / `--format glb`)

- Export assemblies to the Khronos glTF 2.0 format — viewable in Blender,
  three.js / `<model-viewer>` web viewers, Windows 3D Viewer, and game
  engines.
- **`--format glb`** writes the binary container (JSON chunk + BIN chunk);
  **`--format gltf`** writes JSON with a base64 data-URI buffer. Both are
  self-contained: geometry, materials, and hierarchy in a single file.
- Geometry is meshed from the STEP files via the existing STL pipeline,
  scaled from mm to meters, and embedded with flat per-vertex normals.
- Node hierarchy follows the kinematic spanning tree (rigid groups merged
  into a single node with per-part children); a root node rotates the scene
  from Inventor's Z-up to glTF's required Y-up.
- **Skeleton/armature**: a glTF `skin` is emitted whose joints follow the
  kinematic spanning tree. Meshes are rigid-skinned to their bones
  (`JOINTS_0`/`WEIGHTS_0` with all weight on the owning bone) and the skin
  carries inverse-bind matrices, so Blender, Unity, and Unreal import an
  animatable armature with one bone per part. Disable with
  `GLTFWriter(enable_skin=False)`.
  - `JOINTS_0` uses skin-relative indices with UNSIGNED_SHORT components
    (spec-required type; three.js rejects other types), unused VEC4 slots
    zeroed.
  - **Rigid joints = one bone**: parts fused by rigid constraints collapse
    into a single rigid body / single bone (matching Inventor semantics);
    each member keeps its own mesh skinned to the shared bone. Only
    kinematic joints (revolute, slider, ...) create hierarchy edges
    between bones.
  - Vertex data is stored in world space (incl. Y-up root rotation) so the
    rigid-skin algebra `global_joint @ IBM @ v` evaluates exactly at bind
    pose; inverse bind matrices are flattened column-major per glTF spec.
  - Output passes the official Khronos glTF validator with **0 errors**
    (3 informational warnings remain, standard for skeletal hierarchies).
- PBR materials (`pbrMetallicRoughness`) with colors inferred from material
  names (steel, aluminum, plastic, rubber).
- Constraint/joint metadata (type, occurrence names, axis, origin, limits)
  exported in the top-level `extras` field since glTF core has no joint
  concept.
- New `load_stl()` helper parses binary and ASCII STL files for embedding.
- **Web default tolerance 0.5 mm** (URDF/MuJoCo remain 0.1 mm), with angular
  tolerance ramped alongside — rounded parts are angle-dominated, so a
  coarser linear deflection alone would not shrink them.
- **Fixed: mesh tolerance was silently ignored.** cadquery 2.8's
  `Shape.exportStl` passes deflection through the positional
  `BRepMesh_IncrementalMesh` constructor, which does not honor it (a sphere
  produced byte-identical output at tolerance 0.05 and 50).
  `convert_step_to_stl` now uses the OCCT `IMeshTools_Parameters` API
  directly and calls `BRepTools.Clean_s` first so re-meshing at a new
  tolerance is not short-circuited by cached triangulation. In practice:
  a test sphere+cylinder assembly went from 599 KB to 74 KB at 0.5 mm.
- **Known caveat**: `MeshConverter` skips conversion when an STL with the
  expected name already exists in `meshes/`, regardless of the tolerance it
  was produced with. Delete the `meshes/` folder after changing tolerance
  settings (documented in README).
- 26 new tests in `tests/writers/test_gltf.py` (GLB container parsing,
  node hierarchy, mesh embedding with meter scaling, materials, extras,
  rigid groups, STL loader), plus a tolerance-propagation test in
  `test_mesh_converter.py` covering the cadquery bug fix.

---

## [0.2.0] - 2026-03-09

### Closed Kinematic Chain Support

This is a major release that adds full support for **closed kinematic chains**
(4-bar linkages, parallel robots, Stewart platforms, and any assembly where the
joint graph contains cycles).

Previously, the exporter assumed a strict tree topology. If a body appeared as
the child of two joints, the second was silently dropped — losing critical
mechanical relationships. This release detects loops, builds a spanning tree,
and handles loop-closing joints using the correct mechanism for each output
format.

#### New: Kinematic Tree Engine (`model/kinematic_tree.py`)

- **BFS spanning tree** construction from the joint constraint graph.
- **Automatic loop detection**: identifies which joints close kinematic loops
  (cut joints) vs. which form the spanning tree (tree joints).
- **Root selection heuristic**: uses the ground body if specified, otherwise
  picks the most-connected body.
- **Parent/child flip detection**: when the spanning tree assigns roles
  opposite to Inventor's `OccurrenceOne`/`OccurrenceTwo` order, the joint is
  flagged as "flipped" and origin points are transformed to the correct frame.
- **`get_joint_origin_in_child_frame()`**: utility that resolves joint origins
  into the child body's local frame regardless of flip state — uses
  `origin_two` when available, falls back to full coordinate transform.
- **`KinematicTree` dataclass**: `parent_of`, `joint_for`, `children_of`,
  `cut_joints`, `root_bodies`, `flipped`, with `has_loops` property and
  `describe_loops()` for human-readable output.

#### New: Dual Origin Extraction (`extraction/constraints.py`)

- Joint extraction now captures **both** `OriginOne.Point` and
  `OriginTwo.Point` from Inventor's joint definition.
- `ConstraintInfo` gains two new fields:
  - `origin_two`: point from `OriginTwo` (in OccurrenceTwo's local frame).
  - `origin_source`: records whether `origin` came from `"OriginOne"` or
    `"OriginTwo"` (matters when the spanning tree flips parent/child).

#### Changed: MuJoCo Writer — Equality Constraints for Loops

- Replaced internal `_build_kinematic_tree()` with shared `classify_joints()`.
- **Cut joints** are now exported as `<equality>` constraints:
  - **Revolute** cut joints: two `<connect>` constraints offset along the
    joint axis — creates a proper hinge outside the kinematic tree.
  - **Other types**: single `<connect>` (ball joint approximation) or `<weld>`
    when no origin is available.
- Flipped joint origins handled via `get_joint_origin_in_child_frame()`.
- Pure tree assemblies produce identical output to before (no equality section).

#### Changed: URDF Writer — Kinematic Tree + Gazebo Loop Closure

- **Upgraded from flat/fixed structure to a proper kinematic tree.** Links are
  now connected by typed joints (`revolute`, `prismatic`, `planar`, `fixed`)
  instead of all-fixed-to-base_link.
- Joint axis expressed in child link frame. Joint limits exported when available;
  defaults to +/-pi for revolute joints without explicit limits.
- **Closed loops**: cut joints emitted as `<gazebo>` extension tags containing
  SDF `<joint>` elements. These are picked up when Gazebo converts URDF to SDF.
- Warning comment when Gazebo extensions are present.
- Root bodies still get fixed joints to `base_link`.
- Pure tree assemblies produce clean URDF with no Gazebo extensions.

#### Changed: SDF Writer — Native Loop Support

- **Upgraded from flat/fixed structure to a proper kinematic tree** with typed
  joints.
- **All joints** (tree and cut) are emitted as native SDF `<joint>` elements —
  no workarounds needed since SDF supports graph structures.
- Joint axis in child frame, limits included when available.
- Compatibility note for Gazebo Sim (Ignition) which may not support all
  closed-loop configurations.

#### New: ADAMS Writer — Joint Export

- Joints are now exported as ADAMS constraint commands (previously only bodies
  and geometry were exported; joints were silently dropped).
- For each joint:
  - **I-marker** created on the first part at the joint origin.
  - **J-marker** created on the second part at the same world location.
  - Marker z-axis aligned with joint axis via `_axis_to_rotation()`.
  - Marker locations in global frame (mm), orientation as ZXZ Euler (degrees).
- Joint type mapping: `rotational_joint` -> `revolute`,
  `slider_joint` -> `translational`, `cylindrical_joint` -> `cylindrical`,
  `ball_joint` -> `spherical`, `planar_joint` -> `planar`,
  `rigid_joint` -> `fixed`.
- ADAMS handles closed loops natively — all joints exported without
  tree/cut distinction.

#### New: CLI Loop Warnings

- `--warn-loops` / `--no-warn-loops` flag (default: on).
- When closed loops are detected, prints count and descriptions in yellow:
  ```
  Detected 1 closed kinematic loop(s):
    Loop 1: J4 connects c <-> ground (cut joint)
  ```

#### New: Tests

- 21 new tests in `tests/test_kinematic_tree.py` covering:
  - Empty, single-joint, linear chain, star, and 4-bar topologies.
  - Triangle loop, double loop, duplicate joints.
  - Ground body root selection.
  - Rigid and non-kinematic joint filtering.
  - Parent/child flip detection.
  - Origin frame transformation (identity, rotated, fallback).
  - `KinematicTree` properties and `describe_loops()`.

#### Documentation

- `docs/ROADMAP_closed_loops.md`: full design rationale, per-format approach,
  dependency graph, risks and open questions, references.

### Stats

- **10 files** changed/created
- **~1,500 lines** added across source, tests, and documentation
- **118 tests** pass (97 existing + 21 new), 0 regressions

---

## [0.1.0] - 2025

Initial release.

- Export to ADAMS View (.cmd), URDF, SDF, MuJoCo MJCF.
- Assembly extraction via Inventor COM (bodies, transforms, materials, inertia).
- Constraint/joint extraction (axis, origin, limits).
- Rigid group merging (Union-Find).
- STL-to-IPT import (`inventorimport` CLI).
- Mesh conversion (STEP to STL via CadQuery/OCCT).
