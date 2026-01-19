---
phase: 01-core-infrastructure
plan: 02
subsystem: rotation-utilities
tags: [scipy, rotation, quaternion, euler, math]

dependency-graph:
  requires: [01-01]
  provides: [rotation-conversion, format-specific-rotation]
  affects: [02, 03, 06]

tech-stack:
  added: []
  patterns: [scipy-rotation, gimbal-lock-handling]

files:
  created:
    - src/inventor_exporter/core/rotation.py
  modified:
    - src/inventor_exporter/core/__init__.py

decisions:
  - id: scipy-rotation
    choice: "Use scipy.spatial.transform.Rotation for all rotation conversions"
    rationale: "Handles gimbal lock gracefully, supports all Euler conventions, mathematically verified"

metrics:
  duration: "~5 minutes"
  completed: "2026-01-19"
---

# Phase 01 Plan 02: Rotation Utilities Summary

**One-liner:** Rotation matrix to Euler/quaternion conversion using scipy for ADAMS (ZXZ), URDF (RPY), MuJoCo (quaternion) formats.

## What Was Built

Created rotation conversion module that transforms Inventor's 3x3 rotation matrices to format-specific representations:

- **EulerConvention enum:** Defines ADAMS_ZXZ and URDF_RPY conventions
- **rotation_to_euler():** Converts matrix to Euler angles with gimbal lock detection
- **rotation_to_quaternion():** Converts matrix to (w,x,y,z) quaternion
- **rotation_to_format():** High-level wrapper for format-specific conversion
- **extract_rotation_matrix():** Extracts 3x3 rotation from Inventor 4x4 matrix (internal use)

## Key Implementation Details

### Format Conventions

| Format | Convention | Units | Example for Z90 |
|--------|-----------|-------|-----------------|
| ADAMS | ZXZ Euler | degrees | (90, 0, 0) |
| URDF | RPY/ZYX | radians | (1.571, 0, 0) |
| MuJoCo | quaternion | w,x,y,z | (0.707, 0, 0, 0.707) |

### Gimbal Lock Handling

scipy handles gimbal lock by setting the third angle to zero and issuing a warning. The rotation is still mathematically correct. The module logs these warnings for debugging.

## Changes Made

### Task 1: Core Rotation Functions
- Created `rotation.py` with `EulerConvention`, `rotation_to_euler`, `rotation_to_quaternion`
- Verified identity matrix produces zero angles and (1,0,0,0) quaternion

### Task 2: Format-Specific Wrapper
- Added `rotation_to_format()` for ADAMS/URDF/MUJOCO dispatch
- Added `extract_rotation_matrix()` for Inventor COM matrix extraction
- Updated `core/__init__.py` with exports

## Verification Results

All verification tests passed:
- Identity matrix: zero angles, (1,0,0,0) quaternion
- 90-degree rotations on X/Y/Z axes reconstruct correctly from quaternion
- Invalid format raises ValueError

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rotation library | scipy.spatial.transform.Rotation | Handles gimbal lock, all conventions supported, mathematically verified |
| Quaternion format | scalar-first (w,x,y,z) | MuJoCo convention |
| Gimbal lock handling | Log warning, continue | scipy handles gracefully |

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| 1ad59e9 | feat(01-02): create core rotation conversion functions |
| 331b8ef | feat(01-02): add format-specific rotation conversion wrapper |

## Next Phase Readiness

**Ready for:**
- Phase 02: Intermediate Representation (IR) - rotation utilities ready
- Phase 03: ADAMS Writer - ZXZ Euler angles available
- Phase 06: Additional Formats - URDF/MuJoCo rotations ready

**Blockers:** None
