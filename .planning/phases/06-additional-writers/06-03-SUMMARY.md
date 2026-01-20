---
phase: 06-additional-writers
plan: 03
subsystem: writers
tags: [sdf, gazebo, xml, lxml]
dependency-graph:
  requires:
    - 06-01 (mesh conversion infrastructure)
  provides:
    - SDFWriter class
    - SDF format registration
  affects:
    - CLI format list
tech-stack:
  added: []  # lxml already added in 06-01
  patterns:
    - lxml SubElement for XML construction
    - WriterRegistry decorator registration
key-files:
  created:
    - src/inventor_exporter/writers/sdf.py
  modified:
    - src/inventor_exporter/writers/__init__.py
decisions:
  - id: sdf-same-rpy-as-urdf
    choice: "Use same URDF_RPY convention for rotations"
    rationale: "SDF uses same RPY convention as URDF"
  - id: sdf-pose-element
    choice: "Use single <pose> element with 6 space-separated values"
    rationale: "SDF native format, cleaner than URDF's xyz/rpy attributes"
metrics:
  duration: "3 minutes"
  completed: "2026-01-20"
---

# Phase 06 Plan 03: SDF Writer Summary

SDF writer generating valid SDFormat 1.8 XML for Gazebo simulation with proper pose elements and mesh URI references.

## What Was Built

### SDFWriter Class (`src/inventor_exporter/writers/sdf.py`)

The SDF writer implements the FormatWriter protocol and generates Gazebo-compatible SDF 1.8 XML files.

**Key features:**
- `@WriterRegistry.register("sdf")` decorator for auto-registration
- `format_name = "sdf"` and `file_extension = ".sdf"`
- `write()` method validates model, converts meshes, builds XML tree

**XML Structure Generated:**
```xml
<sdf version="1.8">
  <model name="assembly_name">
    <link name="base_link"/>
    <link name="part1">
      <pose relative_to="base_link">x y z roll pitch yaw</pose>
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>...</ixx><ixy>...</ixy>...
        </inertia>
      </inertial>
      <visual name="visual">
        <geometry><mesh><uri>meshes/part1.stl</uri></mesh></geometry>
      </visual>
      <collision name="collision">
        <geometry><mesh><uri>meshes/part1.stl</uri></mesh></geometry>
      </collision>
    </link>
    <joint name="part1_joint" type="fixed">
      <parent>base_link</parent>
      <child>part1</child>
    </joint>
  </model>
</sdf>
```

**Coordinate Conventions:**
- Position: meters (same as IR, no conversion)
- Rotation: RPY radians via `rotation_to_euler(matrix, EulerConvention.URDF_RPY, degrees=False)`
- Mesh paths: Forward slashes for cross-platform URI compatibility

### Package Registration

The `__init__.py` imports the sdf module to trigger decorator-based registration. The writer appears in `WriterRegistry.list_formats()` alongside adams, urdf, and mujoco.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 469451e | feat | add SDF writer for Gazebo format |

Note: Task 2 (package registration) was already committed by a parallel plan execution.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All verification criteria passed:
- `'sdf' in WriterRegistry.list_formats()` - PASS
- `get_writer('sdf').format_name == 'sdf'` - PASS
- `get_writer('sdf').file_extension == '.sdf'` - PASS
- All 78 tests passing - PASS

## Key Differences from URDF Writer

| Aspect | URDF | SDF |
|--------|------|-----|
| Root element | `<robot>` | `<sdf version="1.8"><model>` |
| Position/Rotation | Separate `xyz`, `rpy` attributes | Single `<pose>` element with 6 values |
| Inertia | Attributes on `<inertia>` | Nested child elements |
| Mesh reference | `filename="..."` attribute | `<uri>...</uri>` child element |
| Visual/Collision | No name attribute | `name="visual"`, `name="collision"` |

## Technical Notes

1. **Pose Format**: SDF uses a single `<pose>` element with space-separated "x y z roll pitch yaw" values, which is more compact than URDF's separate xyz/rpy attributes.

2. **Inertia Elements**: SDF nests inertia components as child elements (`<ixx>`, `<ixy>`, etc.) rather than using attributes like URDF.

3. **Mesh URIs**: Uses forward slashes for cross-platform compatibility even on Windows.

4. **MeshConverter Integration**: Reuses the same MeshConverter from 06-01 for STEP to STL conversion.

## Next Phase Readiness

Phase 6 format writers are now complete:
- 06-01: Mesh conversion infrastructure
- 06-02: URDF writer
- 06-03: SDF writer (this plan)
- 06-04: MuJoCo writer

All robot description formats are implemented with consistent patterns and shared mesh conversion infrastructure.
