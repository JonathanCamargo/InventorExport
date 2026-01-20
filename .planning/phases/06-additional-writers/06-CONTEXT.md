# Phase 6: Additional Writers - Context

**Gathered:** 2026-01-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement URDF, SDF, and MuJoCo format writers using the existing FormatWriter plugin architecture. Bodies-only export (joints are v2). Writers transform the intermediate representation to format-specific XML with appropriate coordinate conventions.

</domain>

<decisions>
## Implementation Decisions

### XML Structure
- Preserve assembly hierarchy in output (nest bodies matching Inventor subassembly structure)
- Use Inventor occurrence names (already sanitized in IR)
- Define materials/assets separately, reference by name (like ADAMS writer)
- Include verbose comments: section headers, body explanations, unit reminders

### Geometry Handling
- Reference geometry files with relative paths to output XML location
- Convert STEP to binary STL format during export
- Place converted mesh files in `meshes/` subdirectory relative to output XML
- Each unique part definition gets one mesh file (reused by multiple occurrences)

### Robot Semantics
- Create explicit `base_link` as root body (virtual frame at world origin)
- All physical bodies connect to the kinematic tree via fixed joints (rigid assembly)
- Include collision geometry identical to visual geometry
- Structure supports future joint addition in v2

### Format Specifics
- URDF: Target URDF 1.0 (ROS compatible)
- SDF: Separate writer for Gazebo SDF format
- MuJoCo: Target MuJoCo 3.x MJCF format
- Validate output against format schemas; fail on invalid XML
- Three separate format writers: `urdf`, `sdf`, `mujoco`

### Claude's Discretion
- Kinematic tree structure (fixed joints vs world-attached) for bodies-only
- XML library choice (lxml vs ElementTree)
- STEP-to-STL conversion library/method
- Exact comment formatting and verbosity level
- Schema validation implementation details

</decisions>

<specifics>
## Specific Ideas

- Output should be immediately loadable in target simulators (ROS/Gazebo, MuJoCo)
- Virtual base_link at world origin is standard robot convention
- Mesh files deduplicated by part definition (not per occurrence)

</specifics>

<deferred>
## Deferred Ideas

- Joint extraction from Inventor constraints (v2 scope)
- Simplified collision geometry generation (v2 scope)
- SDF world files with multiple robots (future enhancement)

</deferred>

---

*Phase: 06-additional-writers*
*Context gathered: 2026-01-20*
