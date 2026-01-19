# Architecture Patterns

**Domain:** CAD-to-simulation multi-format exporter
**Researched:** 2026-01-19
**Confidence:** MEDIUM (based on established software patterns; format-specific details require verification)

## Executive Summary

A Python CAD-to-simulation exporter should follow the **Extract-Transform-Load (ETL) pattern** with a clear three-layer architecture:

1. **Extraction Layer** - Pulls data from Autodesk Inventor via COM automation
2. **Intermediate Representation (IR)** - Format-agnostic assembly model
3. **Writer Layer** - Plugin-based format-specific output generators

This separation ensures adding new export formats requires only implementing a new Writer plugin, without modifying extraction or core logic.

## Recommended Architecture

```
+------------------+     +-------------------+     +------------------+
|  Inventor COM    |     |   Intermediate    |     |  Format Writers  |
|  Extraction      | --> |   Representation  | --> |  (Plugins)       |
+------------------+     +-------------------+     +------------------+
        |                        |                         |
   InventorClient         AssemblyModel              WriterProtocol
   - get_assembly()       - bodies: List[Body]       - write(model, path)
   - get_parts()          - joints: List[Joint]
   - get_constraints()    - materials: List[Mat]     ADAMSWriter
   - get_materials()      - meshes: Dict[str,Path]   URDFWriter
                                                     MuJoCoWriter
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `inventor_client` | COM automation, data extraction from Inventor | Intermediate model builder |
| `model` | Format-agnostic assembly representation (dataclasses) | All components read from this |
| `writers/` | Format-specific output generation | Reads from model, writes to filesystem |
| `cli` | User interface, orchestration | Calls client, then writer |
| `geometry/` | Mesh export (STEP/STL), coordinate transforms | Called by client and writers |

### Data Flow

```
User invokes CLI with: --format=adams --output=robot.cmd
                            |
                            v
              +---------------------------+
              |  CLI parses arguments     |
              +---------------------------+
                            |
                            v
              +---------------------------+
              |  InventorClient extracts  |
              |  assembly data via COM    |
              +---------------------------+
                            |
                            v
              +---------------------------+
              |  Build AssemblyModel IR   |
              |  (bodies, joints, mats)   |
              +---------------------------+
                            |
                            v
              +---------------------------+
              |  WriterRegistry.get()     |
              |  returns ADAMSWriter      |
              +---------------------------+
                            |
                            v
              +---------------------------+
              |  writer.write(model, path)|
              |  generates .cmd file      |
              +---------------------------+
```

## Intermediate Representation Design

The IR is the critical architectural element. It must capture enough information for all target formats while remaining format-agnostic.

### Core Data Structures

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import numpy as np

@dataclass
class Transform:
    """6-DOF pose: position + orientation."""
    position: np.ndarray  # [x, y, z] in meters
    rotation: np.ndarray  # 3x3 rotation matrix or quaternion [w, x, y, z]

    @classmethod
    def identity(cls) -> "Transform":
        return cls(np.zeros(3), np.eye(3))

@dataclass
class Material:
    """Physical material properties."""
    name: str
    density: float  # kg/m^3
    youngs_modulus: Optional[float] = None  # Pa
    poissons_ratio: Optional[float] = None

@dataclass
class Inertia:
    """Mass properties."""
    mass: float  # kg
    center_of_mass: np.ndarray  # [x, y, z] relative to body frame
    inertia_tensor: np.ndarray  # 3x3 symmetric matrix

@dataclass
class Body:
    """Rigid body in the assembly."""
    name: str
    transform: Transform  # pose in world frame
    material: Optional[Material] = None
    inertia: Optional[Inertia] = None
    geometry_file: Optional[Path] = None  # path to mesh (STEP/STL)
    parent: Optional[str] = None  # parent body name for tree structure

@dataclass
class Joint:
    """Kinematic connection between bodies."""
    name: str
    joint_type: str  # "revolute", "prismatic", "fixed", "spherical"
    parent_body: str
    child_body: str
    parent_anchor: Transform  # attachment point on parent
    child_anchor: Transform   # attachment point on child
    axis: np.ndarray = field(default_factory=lambda: np.array([0, 0, 1]))
    limits: Optional[tuple[float, float]] = None  # (min, max)

@dataclass
class AssemblyModel:
    """Complete assembly representation."""
    name: str
    bodies: list[Body] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    ground_body: str = "ground"  # name of fixed world frame

    def get_body(self, name: str) -> Optional[Body]:
        return next((b for b in self.bodies if b.name == name), None)

    def validate(self) -> list[str]:
        """Return list of validation errors."""
        errors = []
        body_names = {b.name for b in self.bodies}
        for joint in self.joints:
            if joint.parent_body not in body_names and joint.parent_body != self.ground_body:
                errors.append(f"Joint {joint.name}: unknown parent {joint.parent_body}")
            if joint.child_body not in body_names:
                errors.append(f"Joint {joint.name}: unknown child {joint.child_body}")
        return errors
```

### Why This IR Works

1. **Bodies are first-class** - Every format needs rigid body definitions
2. **Joints capture kinematics** - Maps to ADAMS constraints, URDF joints, MuJoCo joints
3. **Material separation** - Can be shared across bodies (common in CAD)
4. **Transform is explicit** - No ambiguity about coordinate frames
5. **Geometry is external** - Mesh files referenced, not embedded

## Writer Plugin Architecture

### Protocol-Based Interface

Use Python's `Protocol` for static typing without inheritance coupling:

```python
from typing import Protocol, runtime_checkable
from pathlib import Path

@runtime_checkable
class FormatWriter(Protocol):
    """Interface all format writers must implement."""

    format_name: str  # e.g., "adams", "urdf", "mujoco"
    file_extension: str  # e.g., ".cmd", ".urdf", ".xml"

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write model to file."""
        ...

    def validate_model(self, model: AssemblyModel) -> list[str]:
        """Check model compatibility with this format. Return errors."""
        ...
```

### Writer Registry Pattern

Auto-discovery via entry points or explicit registration:

```python
from typing import Type

class WriterRegistry:
    """Central registry for format writers."""

    _writers: dict[str, Type[FormatWriter]] = {}

    @classmethod
    def register(cls, writer_class: Type[FormatWriter]) -> Type[FormatWriter]:
        """Decorator to register a writer."""
        cls._writers[writer_class.format_name] = writer_class
        return writer_class

    @classmethod
    def get(cls, format_name: str) -> FormatWriter:
        """Get writer instance by format name."""
        if format_name not in cls._writers:
            available = ", ".join(cls._writers.keys())
            raise ValueError(f"Unknown format '{format_name}'. Available: {available}")
        return cls._writers[format_name]()

    @classmethod
    def list_formats(cls) -> list[str]:
        """Return all registered format names."""
        return list(cls._writers.keys())

# Usage in writer module:
@WriterRegistry.register
class ADAMSWriter:
    format_name = "adams"
    file_extension = ".cmd"

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        # Implementation
        ...
```

### Alternative: Entry Points (for pip-installable plugins)

For true extensibility where third parties can add formats:

```toml
# pyproject.toml
[project.entry-points."inventorexport.writers"]
adams = "inventorexport.writers.adams:ADAMSWriter"
urdf = "inventorexport.writers.urdf:URDFWriter"
mujoco = "inventorexport.writers.mujoco:MuJoCoWriter"
```

```python
# Dynamic loading
from importlib.metadata import entry_points

def load_writers():
    eps = entry_points(group="inventorexport.writers")
    for ep in eps:
        writer_class = ep.load()
        WriterRegistry._writers[ep.name] = writer_class
```

**Recommendation:** Start with explicit registration (simpler), add entry points later if third-party extensibility becomes a requirement.

## Format-Specific Patterns

### ADAMS View (.cmd)

ADAMS uses a command-script format with specific ordering requirements:

```
1. Model creation
2. Units specification
3. Material definitions
4. Part (rigid body) definitions with:
   - Position/orientation
   - Mass properties
   - Geometry import
5. Marker definitions (reference frames on bodies)
6. Constraint/joint definitions
```

**Key insight from existing VBA:** The current code writes to temporary files (Materials.txt, RigidBodies.txt) then concatenates. Python should use in-memory string building with proper ordering.

### URDF (.urdf)

URDF is XML-based with a strict tree structure:

```xml
<robot name="...">
  <link name="base_link">
    <inertial>...</inertial>
    <visual><geometry>...</geometry></visual>
    <collision><geometry>...</geometry></collision>
  </link>
  <joint name="..." type="revolute">
    <parent link="..."/>
    <child link="..."/>
    <origin xyz="..." rpy="..."/>
    <axis xyz="..."/>
  </joint>
</robot>
```

**Key constraint:** URDF requires a tree structure (no closed loops). May need to break loops for some assemblies.

### MuJoCo (.xml)

MuJoCo MJCF is XML but supports multiple kinematic trees and more joint types:

```xml
<mujoco model="...">
  <asset>
    <mesh file="..."/>
  </asset>
  <worldbody>
    <body name="..." pos="..." euler="...">
      <geom type="mesh" mesh="..."/>
      <joint type="hinge" axis="..."/>
      <body name="...">...</body>  <!-- nested -->
    </body>
  </worldbody>
</mujoco>
```

**Key difference:** MuJoCo uses nested body hierarchy, not explicit parent/child joints.

## Extraction Layer Design

### COM Automation with pywin32

```python
import win32com.client
from contextlib import contextmanager

class InventorClient:
    """Interface to Autodesk Inventor via COM."""

    def __init__(self):
        self._app = None

    @contextmanager
    def connect(self):
        """Context manager for Inventor connection."""
        self._app = win32com.client.Dispatch("Inventor.Application")
        try:
            yield self
        finally:
            self._app = None

    def get_active_assembly(self) -> AssemblyModel:
        """Extract assembly from active document."""
        doc = self._app.ActiveDocument
        if doc.DocumentType != 12291:  # kAssemblyDocumentObject
            raise ValueError("Active document is not an assembly")

        model = AssemblyModel(name=doc.DisplayName)
        comp_def = doc.ComponentDefinition

        # Extract bodies from leaf occurrences
        for occ in comp_def.Occurrences.AllLeafOccurrences:
            body = self._extract_body(occ)
            model.bodies.append(body)

        # Extract joints from constraints
        for constraint in comp_def.Constraints:
            if joint := self._constraint_to_joint(constraint):
                model.joints.append(joint)

        return model

    def _extract_body(self, occurrence) -> Body:
        """Convert Inventor occurrence to Body."""
        transform = self._matrix_to_transform(occurrence.Transformation)
        name = occurrence.Name.replace(":", "_")  # sanitize

        # Get geometry file path
        part_doc = occurrence.Definition.Document
        geo_name = part_doc.DisplayName.rsplit(".", 1)[0]

        return Body(
            name=name,
            transform=transform,
            geometry_file=Path(f"{geo_name}.stp"),
        )

    def _matrix_to_transform(self, matrix) -> Transform:
        """Convert Inventor Matrix to Transform."""
        # Extract translation
        translation = matrix.Translation
        position = np.array([translation.X, translation.Y, translation.Z])
        position *= 0.01  # cm to m

        # Extract rotation (3x3 from 4x4 matrix)
        rotation = np.array([
            [matrix.Cell(1,1), matrix.Cell(1,2), matrix.Cell(1,3)],
            [matrix.Cell(2,1), matrix.Cell(2,2), matrix.Cell(2,3)],
            [matrix.Cell(3,1), matrix.Cell(3,2), matrix.Cell(3,3)],
        ])

        return Transform(position, rotation)
```

### Key Extraction Decisions

1. **All leaf occurrences become bodies** - Matches existing VBA behavior
2. **Constraints map to joints** - Need constraint-type mapping table
3. **Materials extracted from parts** - Deduplicated by name
4. **Geometry exported separately** - STEP files for mesh data

## Patterns to Follow

### Pattern 1: Builder for Complex Objects

Use builders for constructing the IR when extraction is complex:

```python
class AssemblyModelBuilder:
    def __init__(self, name: str):
        self._model = AssemblyModel(name=name)
        self._material_cache: dict[str, Material] = {}

    def add_body(self, name: str, transform: Transform) -> "AssemblyModelBuilder":
        self._model.bodies.append(Body(name=name, transform=transform))
        return self

    def with_material(self, body_name: str, material_name: str,
                      density: float) -> "AssemblyModelBuilder":
        if material_name not in self._material_cache:
            mat = Material(name=material_name, density=density)
            self._material_cache[material_name] = mat
            self._model.materials.append(mat)
        body = self._model.get_body(body_name)
        body.material = self._material_cache[material_name]
        return self

    def build(self) -> AssemblyModel:
        errors = self._model.validate()
        if errors:
            raise ValueError(f"Invalid model: {errors}")
        return self._model
```

### Pattern 2: Visitor for Format-Specific Traversal

Writers may need different traversal orders:

```python
from abc import ABC, abstractmethod

class ModelVisitor(ABC):
    """Visit model elements in format-appropriate order."""

    @abstractmethod
    def visit_model(self, model: AssemblyModel) -> None: ...

    @abstractmethod
    def visit_material(self, material: Material) -> None: ...

    @abstractmethod
    def visit_body(self, body: Body) -> None: ...

    @abstractmethod
    def visit_joint(self, joint: Joint) -> None: ...

class ADAMSVisitor(ModelVisitor):
    """ADAMS needs: materials -> bodies -> joints."""

    def visit_model(self, model: AssemblyModel) -> None:
        for mat in model.materials:
            self.visit_material(mat)
        for body in model.bodies:
            self.visit_body(body)
        for joint in model.joints:
            self.visit_joint(joint)
```

### Pattern 3: Strategy for Coordinate Transforms

Different formats use different conventions:

```python
class CoordinateConvention:
    """Handle coordinate system differences between formats."""

    @staticmethod
    def inventor_to_meters(value_cm: float) -> float:
        return value_cm * 0.01

    @staticmethod
    def rotation_to_euler_xyz(rotation: np.ndarray) -> tuple[float, float, float]:
        """Convert rotation matrix to XYZ Euler angles (radians)."""
        # Implementation varies by convention
        ...

    @staticmethod
    def rotation_to_euler_zyx(rotation: np.ndarray) -> tuple[float, float, float]:
        """ADAMS uses ZYX Euler sequence."""
        ...

    @staticmethod
    def rotation_to_rpy(rotation: np.ndarray) -> tuple[float, float, float]:
        """URDF uses roll-pitch-yaw (XYZ fixed axes)."""
        ...
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Format Logic in Extraction

**What:** Putting ADAMS-specific code in the Inventor extraction layer
**Why bad:** Every new format requires modifying extraction code
**Instead:** Extract to neutral IR, let writers handle format specifics

```python
# BAD
def extract_for_adams(occurrence):
    return f"part create rigid_body name_and_position &\n  part_name = .model_1.{occurrence.Name}"

# GOOD
def extract(occurrence) -> Body:
    return Body(name=occurrence.Name, transform=...)

class ADAMSWriter:
    def write_body(self, body: Body) -> str:
        return f"part create rigid_body name_and_position &\n  part_name = .model_1.{body.name}"
```

### Anti-Pattern 2: String-Based IR

**What:** Using dictionaries or JSON as the intermediate representation
**Why bad:** No type safety, easy to have missing/misspelled keys, hard to refactor
**Instead:** Use typed dataclasses with validation

### Anti-Pattern 3: Monolithic Writer Classes

**What:** Single class with 1000+ lines handling all aspects of format
**Why bad:** Hard to test, hard to extend, violates SRP
**Instead:** Decompose into focused components:

```python
# Decomposed ADAMS writer
class ADAMSMaterialFormatter:
    def format(self, material: Material) -> str: ...

class ADAMSBodyFormatter:
    def format(self, body: Body) -> str: ...

class ADAMSJointFormatter:
    def format(self, joint: Joint) -> str: ...

class ADAMSWriter:
    def __init__(self):
        self._material_fmt = ADAMSMaterialFormatter()
        self._body_fmt = ADAMSBodyFormatter()
        self._joint_fmt = ADAMSJointFormatter()

    def write(self, model: AssemblyModel, path: Path) -> None:
        sections = [
            self._write_header(model),
            *[self._material_fmt.format(m) for m in model.materials],
            *[self._body_fmt.format(b) for b in model.bodies],
            *[self._joint_fmt.format(j) for j in model.joints],
        ]
        path.write_text("\n".join(sections))
```

### Anti-Pattern 4: Tight Coupling to Inventor Types

**What:** Passing Inventor COM objects through the system
**Why bad:** Can't test without Inventor, can't reuse with other CAD sources
**Instead:** Convert to IR immediately at extraction boundary

## Project Structure

```
inventorexport/
|-- __init__.py
|-- __main__.py          # Entry point: python -m inventorexport
|-- cli.py               # Click/argparse CLI definition
|-- model/
|   |-- __init__.py
|   |-- assembly.py      # AssemblyModel, Body, Joint, etc.
|   |-- transform.py     # Transform, coordinate utilities
|   |-- validation.py    # Model validation logic
|-- extraction/
|   |-- __init__.py
|   |-- inventor.py      # InventorClient, COM automation
|   |-- builder.py       # AssemblyModelBuilder
|-- writers/
|   |-- __init__.py      # WriterRegistry, FormatWriter protocol
|   |-- adams.py         # ADAMSWriter
|   |-- urdf.py          # URDFWriter
|   |-- mujoco.py        # MuJoCoWriter
|-- geometry/
|   |-- __init__.py
|   |-- export.py        # STEP/STL mesh export
|   |-- transform.py     # Mesh coordinate transforms
|-- tests/
|   |-- __init__.py
|   |-- conftest.py      # Fixtures, sample models
|   |-- test_model.py
|   |-- test_writers/
|   |   |-- test_adams.py
|   |   |-- test_urdf.py
|   |-- test_extraction.py  # Requires Inventor (integration)
```

## Suggested Build Order

Based on dependencies and testability:

### Phase 1: Core Model (Foundation)

Build first because everything depends on it:
1. `model/transform.py` - Transform class, coordinate utilities
2. `model/assembly.py` - Body, Joint, Material, AssemblyModel
3. `model/validation.py` - Model validation
4. Tests with hand-constructed models

**Why first:** Can be built and tested without Inventor or any format knowledge.

### Phase 2: First Writer (ADAMS)

Build one complete writer to validate the IR design:
1. `writers/__init__.py` - FormatWriter protocol, WriterRegistry
2. `writers/adams.py` - Complete ADAMS .cmd writer
3. Tests with golden file comparison

**Why ADAMS first:** Closest to existing VBA implementation, can validate against known-good output.

### Phase 3: Extraction Layer

Now build extraction, knowing the IR is validated:
1. `extraction/inventor.py` - InventorClient
2. `extraction/builder.py` - AssemblyModelBuilder
3. Integration tests (require Inventor installation)

**Why after writer:** If IR needs changes, better to discover before extraction is built.

### Phase 4: CLI Integration

Wire everything together:
1. `cli.py` - Command-line interface
2. `__main__.py` - Entry point
3. End-to-end testing

### Phase 5: Additional Writers

Add formats in parallel:
1. `writers/urdf.py`
2. `writers/mujoco.py`
3. Format-specific tests

**Why parallel:** Each writer is independent once IR is stable.

### Phase 6: Geometry Pipeline

Add mesh export (may be needed earlier if testing requires it):
1. `geometry/export.py` - STEP export via Inventor
2. `geometry/transform.py` - Coordinate transforms for meshes

## Scalability Considerations

| Concern | Current (single assembly) | Future (batch processing) |
|---------|---------------------------|---------------------------|
| Memory | Hold one AssemblyModel | Stream extraction, write incrementally |
| Performance | Single-threaded COM | Can't parallelize Inventor COM |
| Formats | 3 writers | Entry points for extensibility |
| CAD Sources | Inventor only | Abstract extraction interface |

## Testing Strategy

### Unit Tests (No Inventor Required)

- Model dataclass construction and validation
- Transform math (rotation conversions, coordinate transforms)
- Writer output for hand-constructed models
- Golden file tests for format correctness

### Integration Tests (Inventor Required)

- Extraction from sample .iam files
- Round-trip: extract -> write -> manual verification
- Mark with `@pytest.mark.inventor` for CI skip

### Test Fixtures

```python
@pytest.fixture
def simple_two_body_model():
    """Minimal model: two bodies connected by a revolute joint."""
    return AssemblyModel(
        name="test",
        bodies=[
            Body(name="base", transform=Transform.identity()),
            Body(name="link1", transform=Transform(np.array([0, 0, 0.1]), np.eye(3))),
        ],
        joints=[
            Joint(
                name="joint1",
                joint_type="revolute",
                parent_body="ground",
                child_body="base",
                parent_anchor=Transform.identity(),
                child_anchor=Transform.identity(),
            ),
        ],
    )
```

## Sources

- Existing VBA codebase analysis (Export.bas, Main.bas, Misc.bas)
- Established software architecture patterns: ETL, Protocol-based interfaces, Registry pattern
- Format specifications require verification from official sources:
  - ADAMS View documentation (MSC Software)
  - URDF specification (ROS wiki)
  - MuJoCo MJCF reference (DeepMind)

**Confidence notes:**
- Architecture patterns: HIGH (well-established software engineering)
- Format-specific details: MEDIUM (based on training data, needs verification against current docs)
- Inventor COM API: MEDIUM (based on existing VBA code patterns)
