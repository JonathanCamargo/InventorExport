---
phase: 02-data-model
plan: 02
subsystem: model
tags: [dataclass, body, assembly, validation, ir]

dependency-graph:
  requires: ["02-01"]
  provides: ["complete-ir", "model-validation", "body-dataclass", "assembly-model"]
  affects: ["03-01", "03-02", "04-01"]

tech-stack:
  added: []
  patterns:
    - "Frozen tuple fields for true immutability"
    - "Comprehensive validation returning all errors"
    - "Name sanitization in __post_init__"

key-files:
  created:
    - src/inventor_exporter/model/body.py
    - src/inventor_exporter/model/assembly.py
  modified:
    - src/inventor_exporter/model/__init__.py

decisions:
  - id: body-sanitization
    choice: "Sanitize body names (colons/spaces to underscores)"
    rationale: "Inventor occurrence names contain colons; some formats reject special chars"
  - id: tuple-collections
    choice: "Use tuple[Body, ...] instead of list[Body, ...]"
    rationale: "Frozen dataclass with list still allows list mutation; tuples are immutable"
  - id: validate-all-errors
    choice: "validate() returns list of ALL errors, not just first"
    rationale: "Better UX - fix all issues in one pass instead of iterating"
  - id: material-ref-not-object
    choice: "Body stores material_name (str) not Material object"
    rationale: "Avoids circular dependencies; AssemblyModel owns material lookup"

metrics:
  duration: "~5 minutes"
  completed: "2026-01-19"
---

# Phase 02 Plan 02: Body and AssemblyModel Summary

**One-liner:** Body composes foundation types; AssemblyModel provides complete IR with multi-error validation

## What Was Built

### Body Dataclass (`body.py`)
- Composes Transform (required), optional Material ref, Inertia, geometry_file Path
- Automatic name sanitization: `Part:1 Name` -> `Part_1_Name`
- Validation: empty name rejected with clear ValueError
- Frozen for immutability

### AssemblyModel Dataclass (`assembly.py`)
- Top-level IR container: name, bodies, materials, ground_body
- `tuple[Body, ...]` and `tuple[Material, ...]` for true immutability
- `get_body(name)` and `get_material(name)` lookup methods
- Comprehensive `validate()` returning list of all errors

### Validation Checks (MODEL-06)
1. Assembly name not empty
2. No duplicate body names
3. All body.material_name references exist in materials
4. Bodies with inertia have positive mass
5. Bodies with inertia have symmetric tensor

## Commits

| Hash | Description |
|------|-------------|
| 4de32ee | feat(02-02): create Body dataclass with name sanitization |
| 1e6166a | feat(02-02): create AssemblyModel with comprehensive validation |
| d40f6e9 | feat(02-02): export Body and AssemblyModel from model package |

## Requirements Addressed

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| MODEL-01 | Done | AssemblyModel is single assembly data structure |
| MODEL-02 | Done | Body stores transform, material ref, geometry file, inertia |
| MODEL-06 | Done | validate() catches errors before format writers run |

## Deviations from Plan

None - plan executed exactly as written.

## Key Code Patterns

**Name sanitization with frozen dataclass:**
```python
def __post_init__(self) -> None:
    sanitized = self.name.replace(":", "_").replace(" ", "_")
    object.__setattr__(self, "name", sanitized)
```

**Multi-error validation pattern:**
```python
def validate(self) -> list[str]:
    errors: list[str] = []
    # ... collect all errors ...
    return errors
```

## Usage Example

```python
from inventor_exporter.model import (
    AssemblyModel, Body, Transform, Material, Inertia
)
import numpy as np

steel = Material(name="steel", density=7800)
base = Body(
    name="base",
    transform=Transform(),
    material_name="steel",
    inertia=Inertia(mass=10.0, inertia_tensor=np.diag([1, 1, 1]))
)

assembly = AssemblyModel(
    name="Robot",
    bodies=(base,),
    materials=(steel,),
)

errors = assembly.validate()
assert errors == []  # Valid assembly
```

## Next Phase Readiness

**Phase 3 can now:**
- Receive complete AssemblyModel from extractor
- Iterate over `assembly.bodies` with full type info
- Look up materials via `assembly.get_material(body.material_name)`
- Validate input before writing: `errors = assembly.validate()`

**Interface contract established:**
- Format writers receive `AssemblyModel` as input
- Writers can trust validation has passed if errors == []
- Body.geometry_file points to exported STEP files (Phase 4 creates these)
