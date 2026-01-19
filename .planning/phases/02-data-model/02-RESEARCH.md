# Phase 2: Data Model - Research

**Researched:** 2026-01-19
**Domain:** Python dataclasses for CAD-to-simulation intermediate representation
**Confidence:** HIGH

## Summary

Phase 2 builds the format-agnostic intermediate representation (IR) that captures complete assembly structure. This research confirms that standard Python dataclasses with `__post_init__` validation are the right choice for this project's internal data model - no need for Pydantic since data comes from trusted COM extraction, not external APIs.

The data model must handle numpy arrays for transforms and inertia tensors, requiring careful attention to default_factory patterns. The key technical challenge is inertia tensor reference frame transformation, which requires both rotation and parallel axis theorem application.

**Primary recommendation:** Use frozen dataclasses with `__post_init__` validation, numpy arrays via `field(default_factory=...)`, and explicit validation methods that return error lists rather than raising exceptions.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dataclasses | stdlib | Immutable data containers | Built-in, type-safe, no dependencies |
| numpy | >=1.24 | Matrix/vector operations | Already in project, industry standard |
| scipy | >=1.11 | Rotation math (already used in Phase 1) | Robust gimbal lock handling |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typing | stdlib | Type annotations | All dataclass definitions |
| pathlib | stdlib | Geometry file paths | Body.geometry_file field |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dataclasses | Pydantic | Pydantic adds validation but is overkill for internal data; slower instantiation |
| dataclasses | attrs | More features but another dependency; dataclasses sufficient |
| manual classes | NamedTuple | NamedTuple is immutable but lacks validation hooks |

**No additional installation needed** - all required packages already in pyproject.toml from Phase 1.

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/model/
    __init__.py          # Public API exports
    transform.py         # Transform dataclass
    material.py          # Material dataclass
    inertia.py           # Inertia dataclass with tensor math
    body.py              # Body dataclass
    assembly.py          # AssemblyModel dataclass
    validation.py        # Validation error collection
```

### Pattern 1: Frozen Dataclasses with Post-Init Validation

**What:** Use `@dataclass(frozen=True)` for immutability, `__post_init__` for validation
**When to use:** All model dataclasses (Transform, Material, Inertia, Body, AssemblyModel)
**Example:**
```python
# Source: Python dataclasses documentation
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

@dataclass(frozen=True)
class Material:
    """Physical material properties."""
    name: str
    density: float  # kg/m^3
    youngs_modulus: Optional[float] = None  # Pa
    poissons_ratio: Optional[float] = None

    def __post_init__(self):
        if self.density <= 0:
            raise ValueError(f"density must be positive, got {self.density}")
```

### Pattern 2: NumPy Arrays as Fields

**What:** Use `field(default_factory=...)` for mutable numpy arrays
**When to use:** Transform rotation/position, Inertia tensor, any array field
**Example:**
```python
# Source: Best practice for numpy in dataclasses
from dataclasses import dataclass, field
import numpy as np

def _identity_rotation() -> np.ndarray:
    return np.eye(3)

def _zero_position() -> np.ndarray:
    return np.zeros(3)

@dataclass(frozen=True)
class Transform:
    """6-DOF pose: position + orientation."""
    position: np.ndarray = field(default_factory=_zero_position)
    rotation: np.ndarray = field(default_factory=_identity_rotation)

    def __post_init__(self):
        # Validate shapes
        if self.position.shape != (3,):
            raise ValueError(f"position must be shape (3,), got {self.position.shape}")
        if self.rotation.shape != (3, 3):
            raise ValueError(f"rotation must be shape (3,3), got {self.rotation.shape}")
```

**Important:** With `frozen=True`, you cannot reassign fields, but numpy arrays can still be mutated in-place. For true immutability, create new arrays when transforming.

### Pattern 3: Validation Method Returns Errors List

**What:** `validate()` method returns list of errors instead of raising exceptions
**When to use:** AssemblyModel validation where multiple errors should be collected
**Example:**
```python
# Source: Django-style validation pattern
@dataclass(frozen=True)
class AssemblyModel:
    name: str
    bodies: tuple[Body, ...] = field(default_factory=tuple)
    materials: tuple[Material, ...] = field(default_factory=tuple)
    ground_body: str = "ground"

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty list means valid."""
        errors = []

        if not self.name:
            errors.append("Assembly name is required")

        body_names = {b.name for b in self.bodies}
        if len(body_names) != len(self.bodies):
            errors.append("Duplicate body names detected")

        for body in self.bodies:
            if body.material_name and body.material_name not in {m.name for m in self.materials}:
                errors.append(f"Body '{body.name}' references unknown material '{body.material_name}'")

        return errors
```

### Pattern 4: Inertia Tensor Transformation

**What:** Transform inertia tensor between reference frames using rotation and parallel axis theorem
**When to use:** When body origin differs from center of mass (MODEL-05 requirement)
**Example:**
```python
# Source: Parallel axis theorem - Wikipedia, MIT OCW Dynamics lecture
import numpy as np

def transform_inertia_tensor(
    I_local: np.ndarray,
    R: np.ndarray,
    mass: float,
    displacement: np.ndarray
) -> np.ndarray:
    """
    Transform inertia tensor to new reference frame.

    Args:
        I_local: 3x3 inertia tensor in local frame (typically at CoM)
        R: 3x3 rotation matrix from local to new frame
        mass: Total mass of body
        displacement: Vector from local origin to new origin

    Returns:
        3x3 inertia tensor in new frame

    The transformation has two parts:
    1. Rotation: I' = R @ I @ R.T
    2. Translation (parallel axis theorem): I'' = I' + m*[(d.d)E - d@d.T]
    """
    # Step 1: Rotate the inertia tensor
    I_rotated = R @ I_local @ R.T

    # Step 2: Apply parallel axis theorem for translation
    d = np.asarray(displacement)
    d_dot_d = np.dot(d, d)
    d_outer_d = np.outer(d, d)
    parallel_axis_term = mass * (d_dot_d * np.eye(3) - d_outer_d)

    return I_rotated + parallel_axis_term
```

### Anti-Patterns to Avoid

- **Mutable default arguments:** Never use `rotation: np.ndarray = np.eye(3)` - all instances would share the same array
- **Validation in `__init__`:** Dataclasses auto-generate `__init__`; use `__post_init__` instead
- **Raising on first error:** For complex models, collect all errors before returning
- **Storing Inventor COM objects:** Always convert to numpy/Python types immediately

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rotation matrix validation | Custom orthogonality check | `scipy.spatial.transform.Rotation.from_matrix()` | Handles numerical precision, finds nearest valid rotation |
| Euler angle conversion | Direct trig formulas | Phase 1 rotation.py utilities | Already handles gimbal lock |
| Unit conversion | Inline multiplication | Phase 1 units.py utilities | Centralized, tested |
| Inertia tensor math | Manual formulas | numpy matrix operations | Vectorized, tested |

**Key insight:** Phase 1 already provides rotation and unit conversion utilities. The data model should use them, not duplicate them.

## Common Pitfalls

### Pitfall 1: Inertia Tensor Reference Frame Confusion

**What goes wrong:** Mass properties from Inventor may be at part origin, not center of mass. Using them directly produces incorrect dynamics.
**Why it happens:** Different systems report inertia in different frames; documentation is often unclear.
**How to avoid:**
1. Always document what frame inertia is expressed in
2. Store center_of_mass explicitly in Inertia dataclass
3. Provide transform method for frame conversions
**Warning signs:** Simulation bodies wobble unexpectedly, inertia values seem too large/small

### Pitfall 2: Shared Mutable State in Dataclasses

**What goes wrong:** Multiple bodies share the same numpy array because of mutable default.
**Why it happens:** `field(default=np.zeros(3))` creates one array shared by all instances.
**How to avoid:** Always use `field(default_factory=lambda: np.zeros(3))`
**Warning signs:** Changing one body's position changes others

### Pitfall 3: Validation Too Strict or Too Loose

**What goes wrong:** Validation rejects valid data or accepts invalid data.
**Why it happens:** Not understanding what downstream consumers (writers) actually need.
**How to avoid:**
1. Required fields: name, position, rotation (for Body)
2. Optional fields: material, inertia, geometry_file
3. Cross-reference validation: material names must exist
**Warning signs:** Valid assemblies fail validation; invalid assemblies produce writer errors

### Pitfall 4: Transform Composition Order

**What goes wrong:** Transforms applied in wrong order produce incorrect world positions.
**Why it happens:** Matrix multiplication is not commutative; parent * child vs child * parent matters.
**How to avoid:** Document clearly: `world_transform = parent_transform @ child_transform`
**Warning signs:** Nested assembly parts appear at wrong positions

## Code Examples

Verified patterns from requirements and prior research:

### Complete Inertia Dataclass
```python
# Source: ARCHITECTURE.md, PITFALLS.md Pitfall #9
from dataclasses import dataclass, field
import numpy as np

def _zero_vector() -> np.ndarray:
    return np.zeros(3)

def _zero_tensor() -> np.ndarray:
    return np.zeros((3, 3))

@dataclass(frozen=True)
class Inertia:
    """Mass properties of a rigid body.

    Attributes:
        mass: Total mass in kg
        center_of_mass: CoM position relative to body frame origin, in meters
        inertia_tensor: 3x3 symmetric inertia tensor at CoM, in kg*m^2
    """
    mass: float
    center_of_mass: np.ndarray = field(default_factory=_zero_vector)
    inertia_tensor: np.ndarray = field(default_factory=_zero_tensor)

    def __post_init__(self):
        if self.mass < 0:
            raise ValueError(f"mass must be non-negative, got {self.mass}")
        if self.center_of_mass.shape != (3,):
            raise ValueError(f"center_of_mass must be shape (3,), got {self.center_of_mass.shape}")
        if self.inertia_tensor.shape != (3, 3):
            raise ValueError(f"inertia_tensor must be shape (3,3), got {self.inertia_tensor.shape}")

    def at_point(self, point: np.ndarray) -> np.ndarray:
        """Return inertia tensor transformed to a different point.

        Uses parallel axis theorem: I' = I + m*[(d.d)E - d@d.T]
        where d is displacement from CoM to new point.
        """
        d = point - self.center_of_mass
        d_dot_d = np.dot(d, d)
        d_outer_d = np.outer(d, d)
        return self.inertia_tensor + self.mass * (d_dot_d * np.eye(3) - d_outer_d)

    def rotated(self, R: np.ndarray) -> "Inertia":
        """Return inertia with tensor rotated to new frame.

        Tensor transforms as: I' = R @ I @ R.T
        """
        new_tensor = R @ self.inertia_tensor @ R.T
        new_com = R @ self.center_of_mass
        # Use object.__setattr__ since frozen
        return Inertia(
            mass=self.mass,
            center_of_mass=new_com,
            inertia_tensor=new_tensor
        )
```

### Complete Body Dataclass
```python
# Source: ARCHITECTURE.md IR design
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import numpy as np

@dataclass(frozen=True)
class Body:
    """Rigid body in the assembly.

    Attributes:
        name: Unique identifier (sanitized from Inventor occurrence name)
        transform: Pose in world frame
        material_name: Reference to material in AssemblyModel.materials
        inertia: Mass properties (optional, extracted from Inventor)
        geometry_file: Path to STEP file for this body's geometry
    """
    name: str
    transform: Transform
    material_name: Optional[str] = None
    inertia: Optional[Inertia] = None
    geometry_file: Optional[Path] = None

    def __post_init__(self):
        if not self.name:
            raise ValueError("Body name cannot be empty")
        # Sanitize name for filesystem/format compatibility
        sanitized = self.name.replace(":", "_").replace(" ", "_")
        if sanitized != self.name:
            # Use object.__setattr__ since frozen
            object.__setattr__(self, 'name', sanitized)
```

### AssemblyModel with Validation
```python
# Source: ARCHITECTURE.md, Django validation pattern
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class AssemblyModel:
    """Complete assembly representation.

    This is the intermediate representation that all format writers consume.
    """
    name: str
    bodies: tuple[Body, ...] = field(default_factory=tuple)
    materials: tuple[Material, ...] = field(default_factory=tuple)
    ground_body: str = "ground"

    def get_body(self, name: str) -> Optional[Body]:
        """Find body by name."""
        return next((b for b in self.bodies if b.name == name), None)

    def get_material(self, name: str) -> Optional[Material]:
        """Find material by name."""
        return next((m for m in self.materials if m.name == name), None)

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty list means valid."""
        errors = []

        # Check assembly name
        if not self.name:
            errors.append("Assembly name is required")

        # Check for duplicate body names
        body_names = [b.name for b in self.bodies]
        if len(body_names) != len(set(body_names)):
            duplicates = [n for n in body_names if body_names.count(n) > 1]
            errors.append(f"Duplicate body names: {set(duplicates)}")

        # Check material references
        material_names = {m.name for m in self.materials}
        for body in self.bodies:
            if body.material_name and body.material_name not in material_names:
                errors.append(
                    f"Body '{body.name}' references unknown material '{body.material_name}'"
                )

        # Validate each body's inertia if present
        for body in self.bodies:
            if body.inertia is not None:
                if body.inertia.mass <= 0:
                    errors.append(f"Body '{body.name}' has non-positive mass")
                # Check inertia tensor is symmetric
                I = body.inertia.inertia_tensor
                if not np.allclose(I, I.T, rtol=1e-5):
                    errors.append(f"Body '{body.name}' has non-symmetric inertia tensor")

        return errors
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@dataclass` | `@dataclass(frozen=True, slots=True)` | Python 3.10+ | Immutability + memory/speed |
| Dict-based models | Typed dataclasses | Python 3.7+ | Type safety, IDE support |
| Manual `__init__` validation | `__post_init__` | Python 3.7+ | Cleaner separation |

**Python 3.11+ features available:**
- `slots=True` for dataclasses (memory efficiency)
- Better error messages for validation failures

## Open Questions

Things that could not be fully resolved:

1. **Inertia tensor frame from Inventor**
   - What we know: Inventor provides mass properties via MassProperties object
   - What's unclear: Whether inertia is reported at CoM or part origin
   - Recommendation: Extraction phase should verify empirically with simple test part

2. **Tuple vs List for collections**
   - What we know: `frozen=True` prevents reassignment but lists are still mutable
   - What's unclear: Performance impact of tuple conversion from extraction
   - Recommendation: Use `tuple` for true immutability; extraction converts once

## Sources

### Primary (HIGH confidence)
- [Python dataclasses documentation](https://docs.python.org/3/library/dataclasses.html) - `__post_init__`, frozen, field
- [Parallel axis theorem - Wikipedia](https://en.wikipedia.org/wiki/Parallel_axis_theorem) - Tensor generalization formula
- [SciPy Rotation documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.html) - Matrix operations
- Project ARCHITECTURE.md - IR design patterns
- Project PITFALLS.md - Inertia tensor reference frame issues (Pitfall #9)

### Secondary (MEDIUM confidence)
- [MolSSI Data Validation Tutorial](https://education.molssi.org/type-hints-pydantic-tutorial/chapters/ManualDataValidation.html) - `__post_init__` patterns
- [MIT OCW Dynamics Lecture L26](https://ocw.mit.edu/courses/16-07-dynamics-fall-2009/dd277ec654440f4c2b5b07d6c286c3fd_MIT16_07F09_Lec26.pdf) - Inertia tensor math
- [Real Python Dataclasses Guide](https://realpython.com/python-data-classes/) - Best practices

### Tertiary (LOW confidence)
- [Pybullet Forum - Steiner's Theorem](https://pybullet.org/Bullet/phpBB3/viewtopic.php?t=11137) - Implementation guidance

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using stdlib dataclasses and numpy already in project
- Architecture patterns: HIGH - Based on Python documentation and project ARCHITECTURE.md
- Inertia math: HIGH - Based on well-established physics (parallel axis theorem)
- Validation patterns: MEDIUM - Best practices vary; Django-style chosen for clarity
- Inventor inertia frame: LOW - Requires empirical verification in extraction phase

**Research date:** 2026-01-19
**Valid until:** Stable - dataclasses and numpy APIs are mature
