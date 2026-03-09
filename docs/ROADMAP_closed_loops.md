# Roadmap: Closed Kinematic Chain Support

## Problem Statement

The current exporter assumes a **strict tree topology** for kinematic joints. Each
body has at most one parent, and joints form a tree rooted at the world frame.
This breaks for assemblies containing **closed kinematic chains** (e.g. 4-bar
linkages, parallel robots, Stewart platforms) where the constraint graph has
cycles.

Today, if a body is the child in two joints, only the first is kept and the
second is silently dropped — losing critical mechanical relationships.

---

## Current State

| Component | Status |
|---|---|
| `_build_kinematic_tree()` (MuJoCo) | Dict-based: `parent_of[child] = parent` — second joint to same child overwrites first |
| URDF writer | All links fixed to `base_link` — no kinematic tree at all |
| SDF writer | All links fixed to `base_link` — no kinematic tree at all |
| ADAMS writer | Exports bodies + geometry only, no joint export |
| `ConstraintInfo` | No field for origin source, loop-closing flag, or parent/child role |
| `rigid_groups()` | Union-Find over rigid constraints — orthogonal to loops |

---

## Phase 1: Loop Detection & Spanning Tree

**Goal:** Given the full constraint graph, identify which joints form a spanning
tree (tree joints) and which close loops (cut joints).

### Tasks

1. **Build undirected constraint graph** from `model.constraints` (non-rigid,
   kinematic joints only). Nodes = body names, edges = joints.

2. **Detect cycles** via DFS/BFS. Any back-edge in a DFS traversal is a
   loop-closing edge.

3. **Extract spanning tree** using BFS from the ground body (or heaviest /
   most-connected body as heuristic root). This gives a unique parent for every
   body.

4. **Label each `ConstraintInfo`** as either `tree_joint` or `cut_joint`.
   Cut joints are the ones removed to break cycles.

### Output

New utility in `model/` or `writers/`:

```python
def classify_joints(
    bodies: list[str],
    constraints: list[ConstraintInfo],
    ground: str,
) -> tuple[
    dict[str, str],            # parent_of (spanning tree)
    dict[str, ConstraintInfo], # tree joints (child -> constraint)
    list[ConstraintInfo],      # cut joints (loop-closing)
    dict[str, list[str]],      # children_of
]:
```

### Validation

- On a pure tree assembly (no loops): zero cut joints, identical to current output.
- On a 4-bar linkage (4 bodies, 4 joints): exactly 1 cut joint.

---

## Phase 2: Enhanced Data Model

**Goal:** Extend `ConstraintInfo` and extraction to carry the information writers
need for loop closure.

### Tasks

1. **Add fields to `ConstraintInfo`:**
   ```python
   origin_source: str = "OriginOne"   # which origin the point came from
   origin_two: Optional[tuple[float,float,float]] = None  # second origin point
   axis_source: str = "OriginOne"     # which origin the axis came from
   ```

2. **Extract both origin points** in `_extract_joint()` (constraints.py):
   - Always try `OriginOne.Point` → store in `origin`
   - Always try `OriginTwo.Point` → store in `origin_two`
   - Record which succeeded in `origin_source`

3. **Frame transformation utility:**
   For cut joints, the origin point may be in the wrong body's local frame.
   Add a helper:
   ```python
   def transform_origin_to_child_frame(
       origin_in_parent: tuple, parent_transform: Transform, child_transform: Transform
   ) -> tuple:
       """Convert a point from parent's local frame to child's local frame."""
   ```

### Validation

- Existing tests pass unchanged (new fields have defaults).
- New unit test: extract a joint, verify both `origin` and `origin_two` are populated.

---

## Phase 3: MuJoCo — Equality Constraints for Cut Joints

**Goal:** Closed loops in MuJoCo are modeled by building a spanning tree for the
`<body>` hierarchy, then adding `<equality>` constraints for cut joints.

### Background

MuJoCo does not allow loops in its body tree. The standard approach is:
- Build the body tree from spanning-tree joints
- For each cut joint, add an **equality constraint** that enforces the
  loop-closing relationship

MuJoCo equality constraint types relevant here:
- `<connect>`: Point-to-point constraint (ball joint outside tree). Two connect
  constraints on the same body pair = hinge outside tree.
- `<weld>`: Full 6-DOF weld between two bodies outside tree.
- `<joint>`: Couples joint values (e.g. mimic joints, gear ratios).

### Tasks

1. **Refactor `_build_kinematic_tree()`** to use `classify_joints()` from Phase 1.
   The spanning tree drives body nesting; cut joints become equality constraints.

2. **Map cut joint types to equality constraints:**

   | Cut Joint Type | MuJoCo Equality |
   |---|---|
   | `rotational_joint` | Two `<connect>` on axis endpoints (hinge) |
   | `slider_joint` | `<connect>` + axis alignment |
   | `ball_joint` | Single `<connect>` at origin |
   | `cylindrical_joint` | `<connect>` + free slide along axis |
   | `rigid_joint` (non-rigid loop) | `<weld>` |

3. **Add `<equality>` section** to MuJoCo XML output after `<worldbody>`:
   ```xml
   <equality>
     <connect body1="link_a" body2="link_c"
              anchor="0.05 0.0 0.1" />
   </equality>
   ```

4. **Solver tuning:** Add reasonable defaults for equality constraint solver
   parameters (solimp, solref) so loops don't bounce or drift.

### Validation

- Export a 4-bar linkage assembly.
- Open in MuJoCo viewer → mechanism moves correctly, no constraint drift.
- Compare with hand-authored MuJoCo XML of same mechanism.

---

## Phase 4: URDF — Kinematic Tree + Gazebo Loop Closure

**Goal:** Upgrade URDF writer from flat/fixed structure to a proper kinematic tree,
with Gazebo-compatible loop closure via `<gazebo>` extension tags.

### Background

URDF is strictly tree-based — no loops allowed. The standard workaround:
- Build the tree from spanning-tree joints (like MuJoCo)
- For cut joints, embed `<gazebo>` tags containing SDF `<joint>` elements
  that close the loop when loaded in Gazebo

### Tasks

1. **Build kinematic tree** using `classify_joints()` — same as MuJoCo.
   Replace flat fixed-joint structure with proper parent-child `<joint>` elements.

2. **Map tree joints** to URDF `<joint>` elements:
   ```xml
   <joint name="joint1" type="revolute">
     <parent link="parent_link"/>
     <child link="child_link"/>
     <origin xyz="..." rpy="..."/>
     <axis xyz="..."/>
     <limit lower="..." upper="..." effort="..." velocity="..."/>
   </joint>
   ```

3. **Add `<gazebo>` extension** for each cut joint:
   ```xml
   <gazebo>
     <joint name="loop_closure_1" type="revolute">
       <parent>link_a</parent>
       <child>link_c</child>
       <axis><xyz>0 0 1</xyz></axis>
     </joint>
   </gazebo>
   ```

4. **Emit warning** when cut joints exist: "URDF does not natively support
   closed loops. Loop-closing joints are included as Gazebo extensions."

### Validation

- URDF validates with `check_urdf` tool (ignoring Gazebo extensions).
- Loads correctly in Gazebo with loops closing properly.
- Pure tree assemblies produce clean URDF with no Gazebo hacks.

---

## Phase 5: SDF — Native Loop Support

**Goal:** SDF supports closed kinematic chains natively (graph structure). Export
all joints directly, no cut-joint workaround needed.

### Background

SDF allows multiple joints to share the same child link, enabling closed loops.
However, Gazebo Sim (Ignition) has limitations with links having two parents —
so we still need the spanning tree for ordering, but can emit all joints directly.

### Tasks

1. **Build kinematic tree** for link ordering (root-first traversal).

2. **Emit ALL joints** (both tree and cut) as `<joint>` elements:
   ```xml
   <joint name="loop_joint" type="revolute">
     <parent>link_a</parent>
     <child>link_c</child>
     <axis><xyz>0 0 1</xyz></axis>
   </joint>
   ```

3. **Add `<pose>` elements** with proper frame references for each link.

4. **Test compatibility note:** Add XML comment when cut joints are present,
   warning about Gazebo Sim limitations.

### Validation

- SDF validates against schema.
- Loads in Gazebo Classic with loop closure working.
- Test with Gazebo Sim — document any limitations.

---

## Phase 6: ADAMS — Joint Export

**Goal:** ADAMS handles closed loops natively. Export all joints (no
tree/cut distinction needed).

### Background

ADAMS/View uses a constraint-based formulation, not a tree. Every joint is an
explicit constraint between two parts — loops are natural.

### Tasks

1. **Export joints** in ADAMS command file format:
   ```
   JOINT/1, REVOLUTE
   , I_MARKER/10, J_MARKER/20
   ```

2. **Map joint types** to ADAMS equivalents:
   - `rotational_joint` → `REVOLUTE`
   - `slider_joint` → `TRANSLATIONAL`
   - `cylindrical_joint` → `CYLINDRICAL`
   - `ball_joint` → `SPHERICAL`
   - `rigid_joint` → `FIXED`

3. **Create markers** at joint origins on each connected part.

### Validation

- Import ADAMS command file in ADAMS/View.
- Mechanism simulates correctly with all DOFs matching Inventor assembly.

---

## Phase 7: CLI & UX

### Tasks

1. **`--warn-loops` flag** (default on): Print detected loops and cut joints
   to stderr during export.

2. **`--loop-strategy` flag** for MuJoCo: Choose between `equality` (default)
   or `ignore` (current behavior, drop cut joints silently).

3. **Validation warning** in `AssemblyModel.validate()`: Detect and report
   closed loops with a message like:
   ```
   Warning: Assembly contains 2 closed kinematic loop(s).
   Loop 1: link_a -> link_b -> link_c -> link_a (cut at joint "J3")
   ```

4. **`--debug-loops` flag**: Dump the constraint graph, spanning tree, and
   cut joints as a DOT file for visualization.

---

## Dependency Graph

```
Phase 1 (Loop Detection)
   │
   ├──> Phase 2 (Data Model)
   │       │
   │       ├──> Phase 3 (MuJoCo equality constraints)
   │       ├──> Phase 4 (URDF + Gazebo extensions)
   │       ├──> Phase 5 (SDF native loops)
   │       └──> Phase 6 (ADAMS joint export)
   │
   └──> Phase 7 (CLI & UX) ← can start after Phase 1, finalized after 3-6
```

Phases 3–6 are independent of each other and can be done in any order or in
parallel.

---

## Risks & Open Questions

1. **Spanning tree root selection:** If there's no ground body, which body
   becomes root? Heuristic: most-connected, or heaviest, or user-specified
   via `--root-body`.

2. **Parent/child assignment in cut joints:** For equality constraints (MuJoCo)
   the anchor point must be in the correct body's frame. Need both `origin`
   and `origin_two` from Phase 2.

3. **Occurrence order ambiguity:** Inventor's `OccurrenceOne`/`OccurrenceTwo`
   assignment in joints is arbitrary (depends on user pick order). The
   spanning tree algorithm resolves this properly, but origin frame
   assumptions must be revisited.

4. **Solver stability (MuJoCo):** Equality constraints can cause instability
   if solver parameters are wrong. May need per-mechanism tuning or sensible
   defaults.

5. **Gazebo Sim (Ignition) limitations:** Newer Gazebo may not support links
   with two parent joints. SDF export may need a compatibility mode.

6. **Nested assemblies:** How do closed loops spanning sub-assembly boundaries
   interact with `traverse_assembly_recursive()`? Likely works since we
   flatten to leaf occurrences, but needs testing.

---

## References

- [MuJoCo: Equality Constraints](https://mujoco.readthedocs.io/en/stable/computation/index.html)
- [MuJoCo: Closed Loop Issue #1172](https://github.com/google-deepmind/mujoco/issues/1172)
- [Gazebo: 4-Bar Linkage Tutorial (SDFormat + URDF)](https://classic.gazebosim.org/tutorials?tut=kinematic_loop)
- [URDF Closed Loop Workaround (ros/urdf#13)](https://github.com/ros/urdf/issues/13)
- [2b-t/closed_loop — ROS closed loop workaround](https://github.com/2b-t/closed_loop)
- [Drake: Parse closed kinematic chains from SDF](https://github.com/RobotLocomotion/drake/issues/18803)
