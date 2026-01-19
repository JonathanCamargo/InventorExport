# Phase 3: ADAMS Writer - Research

**Researched:** 2026-01-19
**Domain:** Format Writer Architecture, ADAMS View Command File Syntax
**Confidence:** HIGH (Pattern based on Python official docs, ADAMS syntax from VBA analysis)

## Summary

Phase 3 implements the first format writer to validate the intermediate representation (IR) design and achieve VBA output parity. This requires two components: (1) a FormatWriter Protocol and WriterRegistry for plugin architecture, and (2) an ADAMS-specific writer that generates `.cmd` files matching the existing VBA output.

The FormatWriter Protocol uses Python's `typing.Protocol` for structural subtyping - writers only need to implement the required methods, no explicit inheritance needed. The WriterRegistry uses a simple dictionary-based registry pattern with decorator-based self-registration for clean extensibility.

The ADAMS writer consumes the AssemblyModel from Phase 2 and generates three sections: material definitions, rigid body configurations, and geometry import commands. Position values convert from IR's meters to ADAMS's millimeters using Phase 1's unit conversion. Rotation uses ZXZ Euler angles (degrees) via Phase 1's rotation utilities.

**Primary recommendation:** Use `typing.Protocol` with `@runtime_checkable` for the FormatWriter interface. Keep the ADAMS writer simple - string formatting with f-strings, no complex templating. Test via golden file comparison against VBA output.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typing | stdlib | Protocol for structural subtyping | Built-in, type-safe writer interface |
| pathlib | stdlib | Path handling for output files | Modern path API, cross-platform |
| io.StringIO | stdlib | In-memory string building | Efficient for command file generation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Writer configuration | If writer needs options |
| abc | stdlib | AbstractMethod decorator | If needed with Protocol |
| functools | stdlib | Registry decorator patterns | For writer registration |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Protocol | ABC | ABC requires explicit inheritance; Protocol is more Pythonic |
| f-string formatting | Jinja2 templates | Jinja2 is overkill for simple text; adds dependency |
| dict-based registry | Entry points | Entry points are for cross-package plugins; overkill for built-in writers |

**No additional installation needed** - all required packages already in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/
    writers/
        __init__.py          # Public API: FormatWriter, WriterRegistry, get_writer()
        protocol.py          # FormatWriter Protocol definition
        registry.py          # WriterRegistry singleton, register decorator
        adams.py             # AdamsWriter implementation
```

### Pattern 1: FormatWriter Protocol

**What:** Define writer interface using `typing.Protocol` for structural subtyping.
**When to use:** All format writers (ADAMS, URDF, MuJoCo).
**Example:**
```python
# Source: Python typing.Protocol documentation
from typing import Protocol, runtime_checkable
from pathlib import Path
from inventor_exporter.model import AssemblyModel

@runtime_checkable
class FormatWriter(Protocol):
    """Protocol for format writers.

    Writers implement this interface to export AssemblyModel to
    specific file formats. No explicit inheritance required.
    """

    @property
    def format_name(self) -> str:
        """Unique format identifier (e.g., 'adams', 'urdf')."""
        ...

    @property
    def file_extension(self) -> str:
        """Output file extension (e.g., '.cmd', '.urdf')."""
        ...

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write model to file.

        Args:
            model: The assembly model to export.
            output_path: Destination file path.

        Raises:
            ValueError: If model validation fails.
            IOError: If file cannot be written.
        """
        ...
```

### Pattern 2: WriterRegistry with Decorator

**What:** Central registry for writer discovery with decorator-based registration.
**When to use:** For selecting writers by format name at runtime.
**Example:**
```python
# Source: Python Packaging User Guide - Registry Pattern
from typing import Dict, Type, Optional

class WriterRegistry:
    """Registry for format writers.

    Writers register themselves using the @register decorator.
    """

    _writers: Dict[str, Type[FormatWriter]] = {}

    @classmethod
    def register(cls, format_name: str):
        """Decorator to register a writer class."""
        def decorator(writer_class: Type[FormatWriter]) -> Type[FormatWriter]:
            cls._writers[format_name.lower()] = writer_class
            return writer_class
        return decorator

    @classmethod
    def get(cls, format_name: str) -> Optional[Type[FormatWriter]]:
        """Get writer class by format name."""
        return cls._writers.get(format_name.lower())

    @classmethod
    def list_formats(cls) -> list[str]:
        """List available format names."""
        return sorted(cls._writers.keys())

# Usage:
@WriterRegistry.register("adams")
class AdamsWriter:
    ...
```

### Pattern 3: ADAMS Command Generation

**What:** Generate ADAMS View command file sections using f-string formatting.
**When to use:** For all ADAMS output generation.
**Example:**
```python
# Source: VBA Export.bas analysis
def _generate_material(self, material: Material) -> str:
    """Generate Adams View material create command."""
    # Material density converts from kg/m^3 to kg/mm^3 for ADAMS
    density_kg_mm3 = material.density * 1e-9

    return (
        f"material create  &\n"
        f"   material_name = .{self.model_name}.{material.name}  &\n"
        f"   youngs_modulus = {material.youngs_modulus or 207000}  &\n"
        f"   poissons_ratio = {material.poissons_ratio or 0.29}  &\n"
        f"   density = {density_kg_mm3:.15e}\n"
    )
```

### Pattern 4: Rigid Body Section Generation

**What:** Generate ADAMS rigid body commands with position/orientation.
**When to use:** For each Body in AssemblyModel.
**Example:**
```python
# Source: VBA Export.bas AppendRigidBody function
def _generate_rigid_body(self, body: Body) -> str:
    """Generate Adams View rigid body commands."""
    from inventor_exporter.core.units import InventorUnits
    from inventor_exporter.core.rotation import rotation_to_euler, EulerConvention

    # Convert position from meters to mm
    pos = body.transform.position * 1000  # m to mm

    # Get ZXZ Euler angles in degrees
    angles = rotation_to_euler(
        body.transform.rotation,
        EulerConvention.ADAMS_ZXZ,
        degrees=True
    )

    lines = []

    # Part creation with position
    lines.append(f"part create rigid_body name_and_position  &")
    lines.append(f"   part_name = .{self.model_name}.{body.name}  &")
    lines.append(f"   location = {pos[0]}, {pos[1]}, {pos[2]}  &")
    lines.append(f"   orientation = {angles[0]}d, {angles[1]}d, {angles[2]}d")
    lines.append("")

    # Mass properties if inertia is present
    if body.inertia:
        com = body.inertia.center_of_mass * 1000  # m to mm
        lines.append(f"part create rigid_body mass_properties  &")
        lines.append(f"   part_name = .{self.model_name}.{body.name}  &")
        lines.append(f"   material_type = .{self.model_name}.{body.material_name}  &")
        lines.append(f"   mass = {body.inertia.mass}  &")
        lines.append(f"   center_of_mass_marker = .{self.model_name}.{body.name}.cm  &")
        lines.append(f"   ixx = {body.inertia.inertia_tensor[0,0]}  &")
        lines.append(f"   iyy = {body.inertia.inertia_tensor[1,1]}  &")
        lines.append(f"   izz = {body.inertia.inertia_tensor[2,2]}  &")
        lines.append(f"   ixy = {body.inertia.inertia_tensor[0,1]}  &")
        lines.append(f"   izx = {body.inertia.inertia_tensor[2,0]}  &")
        lines.append(f"   iyz = {body.inertia.inertia_tensor[1,2]}")
        lines.append("")

    return "\n".join(lines)
```

### Pattern 5: Geometry Import Section

**What:** Generate ADAMS geometry file import and attribute commands.
**When to use:** For bodies with geometry_file set.
**Example:**
```python
# Source: VBA Export.bas AppendGeometryProperties function
def _generate_geometry(self, body: Body) -> str:
    """Generate Adams View geometry import commands."""
    if body.geometry_file is None:
        return ""

    # Use STEP file name (relative path in export directory)
    step_file = body.geometry_file.name

    lines = []
    lines.append(f"file geometry read  &")
    lines.append(f"   type_of_geometry = stp  &")
    lines.append(f"   file_name = {step_file}  &")
    lines.append(f"   part_name = .{self.model_name}.{body.name}")
    lines.append("")

    # Material appearance
    if body.material_name:
        lines.append(f"geometry attributes  &")
        lines.append(f"   geometry_name = .{self.model_name}.{body.name}.{step_file.replace('.stp', '')}  &")
        lines.append(f"   color = steel")  # Default color
        lines.append("")

    return "\n".join(lines)
```

### Anti-Patterns to Avoid

- **Hardcoding model name:** VBA hardcodes `.model_1`. Make model_name configurable (default to assembly name).
- **Template engines for simple output:** Jinja2 is overkill for ADAMS commands. Use f-strings.
- **Inheritance-based plugin system:** Use Protocol for structural subtyping, not ABC inheritance.
- **Global mutable state:** WriterRegistry uses class methods, not instance state. Avoid global writer instances.
- **Implicit registration:** Writers must be imported to register. Use explicit imports in `__init__.py`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Euler angle conversion | Manual trig | Phase 1 `rotation_to_euler()` | Handles gimbal lock |
| Unit conversion | Inline `* 1000` | Phase 1 `InventorUnits.length_to_mm()` | Centralized, documented |
| Model validation | Manual checks | `AssemblyModel.validate()` | Comprehensive, tested |
| File writing | Manual open/write | `pathlib.Path.write_text()` | Handles encoding, atomicity |
| String building | `+=` concatenation | `io.StringIO` or list + join | O(n) vs O(n^2) |

**Key insight:** Phase 1 and Phase 2 provide the utilities. The ADAMS writer should be thin - just format conversion and string generation.

## Common Pitfalls

### Pitfall 1: Unit Conversion Errors

**What goes wrong:** Mixing meters (IR) and millimeters (ADAMS) produces parts at wrong scale.
**Why it happens:** IR uses SI units (meters); ADAMS defaults to mm.
**How to avoid:**
1. Convert ALL positions at the write boundary, not during model construction
2. Use explicit conversion functions from Phase 1
3. Document unit expectations in writer docstrings
**Warning signs:** Parts appear 1000x too large or small in ADAMS

### Pitfall 2: Rotation Convention Mismatch

**What goes wrong:** Parts appear rotated incorrectly in ADAMS.
**Why it happens:** ADAMS uses Body 3-1-3 (ZXZ intrinsic) Euler angles in degrees.
**How to avoid:**
1. Use `rotation_to_euler(matrix, EulerConvention.ADAMS_ZXZ, degrees=True)`
2. Verify with simple 90-degree test rotations
3. Compare output against VBA-generated files
**Warning signs:** Parts at 90-degree angles appear wrong; nested assemblies misaligned

### Pitfall 3: Missing Material References

**What goes wrong:** ADAMS errors on missing material definitions.
**Why it happens:** Body references material by name, but material not exported.
**How to avoid:**
1. Call `model.validate()` before writing - catches missing material refs
2. Generate material section BEFORE rigid body section
3. Only export materials that are actually referenced
**Warning signs:** ADAMS import errors about undefined materials

### Pitfall 4: Circular Import Dependencies

**What goes wrong:** `ImportError` when importing writer modules.
**Why it happens:** Writers import model types, protocol imports writers for type hints.
**How to avoid:**
1. Use `TYPE_CHECKING` guard for type-only imports
2. Protocol module should not import writer implementations
3. Keep registry separate from protocol definition
**Warning signs:** Import errors at startup; "cannot import name" errors

### Pitfall 5: Registration Timing

**What goes wrong:** Writer not found in registry.
**Why it happens:** Module not imported, so decorator never executes.
**How to avoid:**
1. Import all built-in writers in `writers/__init__.py`
2. Document that custom writers must be imported before use
3. Consider lazy loading with `importlib` if needed later
**Warning signs:** `WriterRegistry.get("adams")` returns None

## Code Examples

Verified patterns from official sources and project analysis:

### Complete FormatWriter Protocol
```python
# Source: Python typing.Protocol documentation
from typing import Protocol, runtime_checkable
from pathlib import Path

from inventor_exporter.model import AssemblyModel

@runtime_checkable
class FormatWriter(Protocol):
    """Protocol defining the format writer interface.

    Any class implementing these methods/properties satisfies the protocol.
    No explicit inheritance needed (structural subtyping).

    Example implementation:
        class MyWriter:
            format_name = "myformat"
            file_extension = ".mf"

            def write(self, model: AssemblyModel, output_path: Path) -> None:
                # Generate output...
                output_path.write_text(content)
    """

    @property
    def format_name(self) -> str:
        """Unique identifier for this format.

        Used by WriterRegistry for lookup. Lowercase recommended.
        Examples: 'adams', 'urdf', 'mujoco'
        """
        ...

    @property
    def file_extension(self) -> str:
        """File extension including dot.

        Examples: '.cmd', '.urdf', '.xml'
        """
        ...

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write the assembly model to the specified path.

        Implementations should:
        1. Validate the model (model.validate())
        2. Convert units as needed for the format
        3. Generate format-specific content
        4. Write to output_path

        Args:
            model: Validated AssemblyModel to export.
            output_path: Destination file path. Parent directory must exist.

        Raises:
            ValueError: If model validation fails.
            IOError: If file cannot be written.
        """
        ...
```

### Complete WriterRegistry
```python
# Source: Python Packaging User Guide, Registry Pattern
from typing import Dict, Type, Optional, List
import logging

from inventor_exporter.writers.protocol import FormatWriter

logger = logging.getLogger(__name__)


class WriterRegistry:
    """Central registry for format writers.

    Provides registration and lookup of format writers by name.
    Writers register using the @WriterRegistry.register decorator.

    Thread Safety: The registry is populated at import time. After
    initial registration, it is read-only and thread-safe.

    Example:
        @WriterRegistry.register("myformat")
        class MyWriter:
            format_name = "myformat"
            file_extension = ".mf"
            def write(self, model, path): ...

        # Later:
        writer_cls = WriterRegistry.get("myformat")
        writer = writer_cls()
        writer.write(model, output_path)
    """

    _writers: Dict[str, Type[FormatWriter]] = {}

    @classmethod
    def register(cls, format_name: str):
        """Decorator to register a writer class.

        Args:
            format_name: The name to register under (case-insensitive).

        Returns:
            Decorator function that registers the class.

        Example:
            @WriterRegistry.register("adams")
            class AdamsWriter:
                ...
        """
        def decorator(writer_class: Type[FormatWriter]) -> Type[FormatWriter]:
            key = format_name.lower()
            if key in cls._writers:
                logger.warning(
                    f"Overwriting existing writer for format '{key}'"
                )
            cls._writers[key] = writer_class
            logger.debug(f"Registered writer for format '{key}'")
            return writer_class
        return decorator

    @classmethod
    def get(cls, format_name: str) -> Optional[Type[FormatWriter]]:
        """Get a writer class by format name.

        Args:
            format_name: The format name to look up (case-insensitive).

        Returns:
            The writer class, or None if not found.
        """
        return cls._writers.get(format_name.lower())

    @classmethod
    def list_formats(cls) -> List[str]:
        """List all registered format names.

        Returns:
            Sorted list of format names.
        """
        return sorted(cls._writers.keys())

    @classmethod
    def get_or_raise(cls, format_name: str) -> Type[FormatWriter]:
        """Get a writer class, raising if not found.

        Args:
            format_name: The format name to look up.

        Returns:
            The writer class.

        Raises:
            KeyError: If format is not registered.
        """
        writer_cls = cls.get(format_name)
        if writer_cls is None:
            available = ", ".join(cls.list_formats())
            raise KeyError(
                f"Unknown format '{format_name}'. "
                f"Available formats: {available}"
            )
        return writer_cls
```

### Complete AdamsWriter Implementation
```python
# Source: VBA Export.bas analysis + ADAMS View Command Reference
from pathlib import Path
from typing import Optional
import io

from inventor_exporter.model import AssemblyModel, Body, Material
from inventor_exporter.core.units import InventorUnits
from inventor_exporter.core.rotation import rotation_to_euler, EulerConvention
from inventor_exporter.writers.registry import WriterRegistry


@WriterRegistry.register("adams")
class AdamsWriter:
    """ADAMS View command file writer.

    Generates .cmd files compatible with MSC ADAMS View.
    Output matches VBA implementation (Inventor2AdamsView.ivb).

    Coordinate conventions:
        - Position: millimeters (converted from IR meters)
        - Rotation: ZXZ Euler angles in degrees
        - Density: kg/mm^3 (converted from IR kg/m^3)

    Output structure:
        1. Material definitions (material create commands)
        2. Rigid body definitions (part create rigid_body commands)
        3. Geometry imports (file geometry read commands)
    """

    format_name: str = "adams"
    file_extension: str = ".cmd"

    def __init__(self, model_name: Optional[str] = None):
        """Initialize ADAMS writer.

        Args:
            model_name: ADAMS model name. If None, uses assembly name.
                Will be prefixed with 'model_' if doesn't start with it.
        """
        self._model_name_override = model_name

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write assembly model to ADAMS View command file.

        Args:
            model: AssemblyModel to export.
            output_path: Destination .cmd file path.

        Raises:
            ValueError: If model validation fails.
        """
        # Validate model first
        errors = model.validate()
        if errors:
            raise ValueError(
                f"Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Determine model name
        model_name = self._get_model_name(model)

        # Generate content
        content = self._generate_content(model, model_name)

        # Write to file
        output_path.write_text(content, encoding="utf-8")

    def _get_model_name(self, model: AssemblyModel) -> str:
        """Get ADAMS model name from override or assembly name."""
        if self._model_name_override:
            return self._model_name_override
        # Default: use assembly name, prefixed with model_
        name = model.name.replace(" ", "_").replace("-", "_")
        if not name.startswith("model_"):
            name = f"model_{name}"
        return name

    def _generate_content(self, model: AssemblyModel, model_name: str) -> str:
        """Generate complete command file content."""
        output = io.StringIO()

        # Header comment
        output.write(f"! ADAMS View command file generated by inventor-exporter\n")
        output.write(f"! Assembly: {model.name}\n")
        output.write(f"! Model: {model_name}\n")
        output.write("!\n\n")

        # Materials section
        output.write("! === Materials ===\n")
        for material in model.materials:
            output.write(self._generate_material(material, model_name))
            output.write("\n")

        # Rigid bodies section
        output.write("! === Rigid Bodies ===\n")
        for body in model.bodies:
            output.write(self._generate_rigid_body(body, model_name))
            output.write("\n")

        # Geometry section
        output.write("! === Geometry ===\n")
        for body in model.bodies:
            if body.geometry_file:
                output.write(self._generate_geometry(body, model_name))
                output.write("\n")

        return output.getvalue()

    def _generate_material(self, material: Material, model_name: str) -> str:
        """Generate material create command."""
        # Convert density from kg/m^3 to kg/mm^3 for ADAMS
        density_kg_mm3 = material.density * 1e-9

        # Use defaults if not specified (matching VBA behavior)
        youngs = material.youngs_modulus if material.youngs_modulus else 207000.0
        poissons = material.poissons_ratio if material.poissons_ratio else 0.29

        return (
            f"material create  &\n"
            f"   material_name = .{model_name}.{material.name}  &\n"
            f"   youngs_modulus = {youngs:.6e}  &\n"
            f"   poissons_ratio = {poissons}  &\n"
            f"   density = {density_kg_mm3:.15e}\n"
        )

    def _generate_rigid_body(self, body: Body, model_name: str) -> str:
        """Generate rigid body commands."""
        lines = []

        # Convert position from meters to mm
        pos_mm = body.transform.position * 1000.0

        # Get ZXZ Euler angles in degrees
        angles = rotation_to_euler(
            body.transform.rotation,
            EulerConvention.ADAMS_ZXZ,
            degrees=True
        )

        # Part creation with name and position
        lines.append(f"part create rigid_body name_and_position  &")
        lines.append(f"   part_name = .{model_name}.{body.name}  &")
        lines.append(f"   location = {pos_mm[0]:.6f}, {pos_mm[1]:.6f}, {pos_mm[2]:.6f}  &")
        lines.append(f"   orientation = {angles[0]:.6f}d, {angles[1]:.6f}d, {angles[2]:.6f}d")
        lines.append("")

        # Mass properties (if inertia present)
        if body.inertia and body.material_name:
            lines.extend(self._generate_mass_properties(body, model_name))

        return "\n".join(lines)

    def _generate_mass_properties(self, body: Body, model_name: str) -> list[str]:
        """Generate mass properties command for body with inertia."""
        lines = []
        inertia = body.inertia

        # Inertia tensor components (already in kg*m^2, convert to kg*mm^2)
        # kg*m^2 * (1000 mm/m)^2 = kg*mm^2 * 1e6
        I = inertia.inertia_tensor * 1e6

        lines.append(f"part create rigid_body mass_properties  &")
        lines.append(f"   part_name = .{model_name}.{body.name}  &")
        lines.append(f"   material_type = .{model_name}.{body.material_name}  &")
        lines.append(f"   mass = {inertia.mass:.6f}  &")
        lines.append(f"   ixx = {I[0,0]:.6e}  &")
        lines.append(f"   iyy = {I[1,1]:.6e}  &")
        lines.append(f"   izz = {I[2,2]:.6e}  &")
        lines.append(f"   ixy = {I[0,1]:.6e}  &")
        lines.append(f"   izx = {I[2,0]:.6e}  &")
        lines.append(f"   iyz = {I[1,2]:.6e}")
        lines.append("")

        return lines

    def _generate_geometry(self, body: Body, model_name: str) -> str:
        """Generate geometry import commands."""
        if body.geometry_file is None:
            return ""

        step_file = body.geometry_file.name

        lines = []
        lines.append(f"file geometry read  &")
        lines.append(f"   type_of_geometry = stp  &")
        lines.append(f"   file_name = {step_file}  &")
        lines.append(f"   part_name = .{model_name}.{body.name}")
        lines.append("")

        return "\n".join(lines)
```

### Writers Package __init__.py
```python
# Source: Best practice for package organization
"""Writers package - format writers for exporting AssemblyModel.

This package provides:
    - FormatWriter: Protocol defining the writer interface
    - WriterRegistry: Central registry for format lookup
    - get_writer(): Convenience function to get writer by name

Built-in writers:
    - adams: ADAMS View .cmd files

Example:
    from inventor_exporter.writers import get_writer

    writer = get_writer("adams")
    writer.write(model, Path("output.cmd"))
"""

from inventor_exporter.writers.protocol import FormatWriter
from inventor_exporter.writers.registry import WriterRegistry

# Import built-in writers to trigger registration
from inventor_exporter.writers import adams  # noqa: F401


def get_writer(format_name: str) -> FormatWriter:
    """Get an instantiated writer by format name.

    Args:
        format_name: The format name (e.g., 'adams').

    Returns:
        Instantiated writer ready to use.

    Raises:
        KeyError: If format is not registered.
    """
    writer_cls = WriterRegistry.get_or_raise(format_name)
    return writer_cls()


__all__ = [
    "FormatWriter",
    "WriterRegistry",
    "get_writer",
]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ABC inheritance | typing.Protocol | Python 3.8+ | Structural subtyping, no inheritance needed |
| Entry points for plugins | Simple registry | Always valid for internal plugins | Simpler for built-in writers |
| String concatenation | f-strings + StringIO | Python 3.6+ | Cleaner, more readable |
| Manual validation | dataclass + validate() | Phase 2 | Comprehensive error collection |

**Python 3.11+ features available:**
- `@runtime_checkable` for Protocol isinstance checks
- Better error messages for Protocol violations
- `Self` type for factory methods (if needed)

## Open Questions

Things that could not be fully resolved:

1. **ADAMS exact number formatting**
   - What we know: VBA uses default VBA number formatting
   - What's unclear: Exact precision ADAMS expects for coordinates/angles
   - Recommendation: Use `.6f` for positions, `.6e` for small values, test with ADAMS

2. **Inertia tensor units**
   - What we know: IR uses kg*m^2, ADAMS uses kg*mm^2
   - What's unclear: Whether VBA does this conversion correctly
   - Recommendation: Verify with known test case; conversion factor is 1e6

3. **Model name conventions**
   - What we know: VBA hardcodes `.model_1`
   - What's unclear: ADAMS naming rules/restrictions
   - Recommendation: Allow override, default to assembly name with prefix

## Sources

### Primary (HIGH confidence)
- [Python typing.Protocol documentation](https://typing.python.org/en/latest/spec/protocol.html) - Protocol definition syntax
- [Python Packaging User Guide - Plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) - Registry patterns
- [Real Python - Protocols](https://realpython.com/python-protocol/) - Structural subtyping patterns
- Project VBA codebase - `Export.bas` ADAMS command syntax
- Project Phase 1 research - Rotation and unit conversion

### Secondary (MEDIUM confidence)
- [mypy Protocols documentation](https://mypy.readthedocs.io/en/stable/protocols.html) - Type checking behavior
- [ADAMS View Command Reference](https://help-be.hexagonmi.com/bundle/Adams_2023.4.1_Adams_View_Command_User_Guide/raw/resource/enus/Adams_2023.4.1_Adams_View_Command_User_Guide.pdf) - Command syntax (linked, not fetched)
- [ADAMS Tutorial](https://mecheng.iisc.ac.in/~asitava/NPTEL/adams-tutorial.pdf) - General ADAMS patterns

### Tertiary (LOW confidence)
- Training data knowledge of ADAMS format details - Needs validation against VBA output

## Metadata

**Confidence breakdown:**
- FormatWriter Protocol: HIGH - Based on official Python typing docs
- WriterRegistry pattern: HIGH - Well-established Python pattern
- ADAMS command syntax: HIGH - Derived from VBA codebase analysis
- Unit conversions: MEDIUM - Logic clear, exact precision needs testing
- Number formatting: MEDIUM - Following VBA patterns, needs validation

**Research date:** 2026-01-19
**Valid until:** 90 days (stable patterns, Python typing is mature)
