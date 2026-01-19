---
phase: 02-data-model
plan: 01
subsystem: model
tags: [dataclass, numpy, inertia, transform]

dependency_graph:
  requires: [01-01, 01-02]
  provides: [Transform, Material, Inertia]
  affects: [02-02, 02-03]

tech_stack:
  added: []
  patterns: [frozen-dataclass, default-factory, post-init-validation]

key_files:
  created:
    - src/inventor_exporter/model/__init__.py
    - src/inventor_exporter/model/transform.py
    - src/inventor_exporter/model/material.py
    - src/inventor_exporter/model/inertia.py
  modified: []

decisions:
  - id: frozen-dataclass
    choice: "Use frozen=True for all model dataclasses"
    rationale: "Immutability ensures data integrity through export pipeline"
  - id: tensor-at-com
    choice: "Store inertia tensor at center of mass, provide at_point() for translation"
    rationale: "Standard physics convention; parallel axis theorem for body origin"

metrics:
  duration: 2m
  completed: 2026-01-19
---

# Phase 02 Plan 01: Foundation Dataclasses Summary

**One-liner:** Frozen dataclasses for Transform (pose), Material (density), and Inertia (tensor with parallel axis theorem).

## What Was Built

Created the foundation dataclasses for the intermediate representation (IR):

1. **Transform** (`transform.py`)
   - 6-DOF pose: position (3,) + rotation (3,3)
   - Default factories for numpy arrays (zero position, identity rotation)
   - Shape validation in `__post_init__`

2. **Material** (`material.py`)
   - Required: name (non-empty), density (positive, kg/m^3)
   - Optional: youngs_modulus (Pa), poissons_ratio
   - Validation for positive density and non-empty name

3. **Inertia** (`inertia.py`)
   - Stores mass, center_of_mass, inertia_tensor
   - `at_point(point)`: Returns tensor at different reference point using parallel axis theorem
   - `rotated(R)`: Returns new Inertia with tensor rotated via R @ I @ R.T
   - Addresses MODEL-05 requirement for reference frame transformations

4. **Package exports** (`__init__.py`)
   - All three classes exported from `inventor_exporter.model`
   - Follows same pattern as core module

## Key Implementation Details

### Parallel Axis Theorem (at_point)
```python
d = point - self.center_of_mass
d_dot_d = np.dot(d, d)
d_outer_d = np.outer(d, d)
parallel_axis_term = self.mass * (d_dot_d * np.eye(3) - d_outer_d)
return self.inertia_tensor + parallel_axis_term
```

### Tensor Rotation (rotated)
```python
new_tensor = R @ self.inertia_tensor @ R.T
new_com = R @ self.center_of_mass
return Inertia(mass=self.mass, center_of_mass=new_com, inertia_tensor=new_tensor)
```

## Commits

| Hash | Description |
|------|-------------|
| e7cd610 | feat(02-01): create Transform and Material dataclasses |
| b4dec2e | feat(02-01): create Inertia dataclass with tensor transformations |
| d906427 | feat(02-01): export model package public API |

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All success criteria verified:
- Transform stores position (3,) and rotation (3,3) with shape validation
- Material stores name, density with positive validation, optional youngs/poissons
- Inertia stores mass, CoM, tensor with at_point() and rotated() methods
- Parallel axis theorem correctly increases off-axis inertia
- Rotation correctly transforms tensor via R @ I @ R.T
- All three importable from inventor_exporter.model

## Next Plan Readiness

Ready for 02-02-PLAN.md (Body dataclass):
- Transform available for Body.transform field
- Material available for material_name reference
- Inertia available for Body.inertia field
