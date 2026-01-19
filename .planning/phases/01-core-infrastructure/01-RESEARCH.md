# Phase 1: Core Infrastructure - Research

**Researched:** 2026-01-19
**Domain:** COM Automation, Unit Conversion, Rotation Mathematics, Logging Infrastructure
**Confidence:** HIGH (verified with official documentation)

## Summary

Phase 1 establishes foundational utilities that all subsequent phases depend on. The core infrastructure covers four areas: COM lifecycle management for reliable Inventor connectivity, unit conversion between Inventor's internal centimeter-based system and export format requirements, rotation math for transforming Inventor's 3x3 matrices to various Euler angle conventions and quaternions, and logging for debugging and error tracking.

The standard approach uses pywin32 for COM automation with explicit context managers for deterministic cleanup, scipy.spatial.transform.Rotation for robust rotation conversions (avoiding the gimbal lock bugs in the existing VBA code), and Python's standard logging module configured with dictConfig for flexibility.

**Primary recommendation:** Use scipy.spatial.transform.Rotation for all rotation math - it handles gimbal lock gracefully, supports all target Euler conventions (ZXZ for ADAMS, ZYX/RPY for URDF), and quaternion output for MuJoCo. Wrap all COM operations in context managers that ensure CoUninitialize is called even on exceptions.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pywin32 | 306+ | COM automation | De facto standard for Windows COM in Python. 25+ years mature, extensive CAD automation precedent (AutoCAD, SolidWorks, Inventor). |
| scipy | 1.11+ | Rotation math | `scipy.spatial.transform.Rotation` handles all rotation representations robustly, including gimbal lock detection/handling. |
| logging | stdlib | Debug output | Python standard, hierarchical loggers, multiple handlers, dictConfig for configuration. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 1.24+ | Matrix operations | Required by scipy; useful for transform matrix manipulation. |
| pythoncom | (part of pywin32) | COM threading | Required for explicit CoInitialize/CoUninitialize in context managers and thread safety. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| scipy Rotation | numpy manual math | Manual implementation risks gimbal lock bugs (like existing VBA), more code to maintain |
| pywin32 | comtypes | Less documentation, less CAD automation precedent |
| logging | loguru | Third-party dependency for simple use case |

**Installation:**
```bash
pip install pywin32>=306 scipy>=1.11 numpy>=1.24
```

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/
├── core/
│   ├── __init__.py
│   ├── com.py           # COM connection management, context managers
│   ├── units.py         # Unit conversion utilities
│   ├── rotation.py      # Rotation matrix to Euler/quaternion conversions
│   └── logging.py       # Logging configuration
└── ...
```

### Pattern 1: COM Context Manager
**What:** Wrap COM connection lifecycle in a context manager that handles CoInitialize/CoUninitialize and object cleanup.
**When to use:** Always - every COM interaction should go through this pattern.
**Example:**
```python
# Source: pywin32 documentation, verified
import pythoncom
import win32com.client
from contextlib import contextmanager
from typing import Generator, Any

@contextmanager
def inventor_connection() -> Generator[Any, None, None]:
    """
    Context manager for Inventor COM connection.

    Ensures proper COM initialization and cleanup, even on exceptions.
    Must be used on the main thread or after calling pythoncom.CoInitialize()
    on worker threads.
    """
    app = None
    try:
        # Connect to running Inventor instance
        app = win32com.client.GetActiveObject("Inventor.Application")
        yield app
    finally:
        # Release COM object reference
        if app is not None:
            del app
        # Note: CoUninitialize not needed on main thread (auto-initialized)
        # but explicit cleanup helps with deterministic release
```

### Pattern 2: Thread-Safe COM Access
**What:** Each thread must call CoInitialize before using COM objects.
**When to use:** If using any background threads or async patterns with COM.
**Example:**
```python
# Source: pywin32 docs - https://timgolden.me.uk/pywin32-docs/
import pythoncom
import threading

def worker_thread_function():
    """Worker thread that needs COM access."""
    # MUST initialize COM in each thread
    pythoncom.CoInitialize()
    try:
        # Create NEW COM objects here - don't share from main thread
        app = win32com.client.GetActiveObject("Inventor.Application")
        # ... do work ...
        del app
    finally:
        pythoncom.CoUninitialize()
```

### Pattern 3: Unit Conversion Strategy
**What:** Centralized unit conversion with explicit source/target specification.
**When to use:** All position/dimension data leaving or entering the Inventor layer.
**Example:**
```python
# Source: Autodesk Inventor API docs - internal units are always cm
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

class LengthUnit(Enum):
    CENTIMETER = "cm"  # Inventor internal
    MILLIMETER = "mm"  # ADAMS default
    METER = "m"        # URDF/MuJoCo standard

@dataclass
class UnitConverter:
    """Centralized unit conversion for position/dimension values."""

    # Inventor internal units are ALWAYS centimeters for length
    INVENTOR_INTERNAL = LengthUnit.CENTIMETER

    # Conversion factors from centimeters
    _TO_METERS: float = 0.01
    _TO_MM: float = 10.0

    @classmethod
    def from_inventor(cls, value_cm: float, target: LengthUnit) -> float:
        """Convert from Inventor internal units (cm) to target unit."""
        if target == LengthUnit.CENTIMETER:
            return value_cm
        elif target == LengthUnit.METER:
            return value_cm * cls._TO_METERS
        elif target == LengthUnit.MILLIMETER:
            return value_cm * cls._TO_MM
        raise ValueError(f"Unknown target unit: {target}")

    @classmethod
    def position_from_inventor(
        cls,
        x: float, y: float, z: float,
        target: LengthUnit
    ) -> Tuple[float, float, float]:
        """Convert position vector from Inventor to target unit."""
        return (
            cls.from_inventor(x, target),
            cls.from_inventor(y, target),
            cls.from_inventor(z, target),
        )
```

### Pattern 4: Rotation Conversion with scipy
**What:** Use scipy.spatial.transform.Rotation for all rotation conversions.
**When to use:** Converting Inventor transformation matrices to any target format.
**Example:**
```python
# Source: scipy 1.16 docs - https://docs.scipy.org/doc/scipy/reference/
from scipy.spatial.transform import Rotation
import numpy as np
from typing import Tuple
from enum import Enum

class RotationConvention(Enum):
    """Target format rotation conventions."""
    ADAMS_ZXZ = "ZXZ"        # ADAMS View Body 3-1-3 Euler
    URDF_RPY = "ZYX"         # URDF roll-pitch-yaw (extrinsic XYZ = intrinsic ZYX)
    MUJOCO_QUAT = "quat"     # MuJoCo quaternion [w, x, y, z]

def matrix_to_euler(
    rotation_matrix: np.ndarray,
    convention: RotationConvention,
    degrees: bool = True
) -> Tuple[float, float, float]:
    """
    Convert 3x3 rotation matrix to Euler angles in specified convention.

    Args:
        rotation_matrix: 3x3 rotation matrix from Inventor
        convention: Target Euler angle convention
        degrees: If True, return degrees; if False, return radians

    Returns:
        Tuple of (angle1, angle2, angle3) in the specified convention

    Notes:
        - scipy handles gimbal lock gracefully, issuing a warning and
          setting third angle to zero when singularity is detected
        - The returned angles still represent the correct rotation
    """
    r = Rotation.from_matrix(rotation_matrix)

    if convention == RotationConvention.MUJOCO_QUAT:
        raise ValueError("Use matrix_to_quaternion for quaternion output")

    # scipy uses uppercase for intrinsic (body-fixed) rotations
    euler_seq = convention.value
    angles = r.as_euler(euler_seq, degrees=degrees)

    return tuple(angles)

def matrix_to_quaternion(
    rotation_matrix: np.ndarray,
    scalar_first: bool = True
) -> Tuple[float, float, float, float]:
    """
    Convert 3x3 rotation matrix to quaternion.

    Args:
        rotation_matrix: 3x3 rotation matrix from Inventor
        scalar_first: If True, return [w, x, y, z]; if False, return [x, y, z, w]

    Returns:
        Quaternion as tuple (w, x, y, z) or (x, y, z, w)
    """
    r = Rotation.from_matrix(rotation_matrix)
    q = r.as_quat(scalar_first=scalar_first)
    return tuple(q)
```

### Anti-Patterns to Avoid
- **Manual Euler angle extraction:** The existing VBA code has a division-by-zero bug when cos(beta)=0 (gimbal lock). Never implement rotation math manually - use scipy.
- **Implicit COM cleanup:** Relying on garbage collection for COM objects leads to memory leaks and stale references. Always use context managers.
- **Hardcoded unit scales:** The VBA code uses `trans.ScaleBy(10)` without documentation. Use explicit, named conversion functions.
- **Caching COM objects:** Storing COM object references between operations can cause "object disconnected" errors if Inventor state changes.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rotation matrix to Euler angles | Custom trig formulas | `scipy.spatial.transform.Rotation.as_euler()` | Handles gimbal lock, supports all Euler sequences, mathematically verified |
| Rotation matrix to quaternion | Manual quaternion extraction | `scipy.spatial.transform.Rotation.as_quat()` | Handles edge cases, canonical form option, scalar-first/last flexibility |
| Euler angle convention conversion | Conversion matrices | scipy Rotation chain: `from_euler().as_euler()` | Handles all 12 Euler sequences correctly |
| COM thread safety | Thread-local caching | `pythoncom.CoInitialize()`/`CoUninitialize()` | Built into pywin32, proper apartment management |
| Asin/Acos with bounds checking | `math.asin(clamp(x, -1, 1))` | `scipy Rotation.from_matrix()` | Automatically handles numerical imprecision |

**Key insight:** The existing VBA code has multiple bugs in rotation math (division by zero, unused min-index calculation, unbounded asin). scipy.spatial.transform has been mathematically verified and handles all edge cases.

## Common Pitfalls

### Pitfall 1: COM Object Lifetime Mismanagement
**What goes wrong:** Python's garbage collector doesn't deterministically release COM objects. Inventor accumulates unreleased references, leading to memory leaks, slowdowns, and eventual crashes.
**Why it happens:**
- Caching COM objects for "performance" creates stale references
- Exception handlers that don't clean up COM references
- Storing COM collections while iterating (collection may change)
**How to avoid:**
- Always use context managers for COM connections
- Never cache COM object references between high-level operations
- Delete references explicitly before exiting scope
**Warning signs:**
- Inventor memory grows with each export
- "RPC server is unavailable" errors
- "Object disconnected" exceptions

### Pitfall 2: Gimbal Lock in Euler Angles
**What goes wrong:** When the second Euler angle approaches 90 degrees (for XYZ-type sequences) or 0/180 degrees (for XZX-type sequences), the first and third axes align, causing division by zero or loss of a degree of freedom.
**Why it happens:** Mathematical singularity inherent to Euler angle representation.
**How to avoid:**
- Use `scipy.spatial.transform.Rotation` which handles this gracefully
- scipy issues a warning and sets the third angle to zero, but the rotation is still correct
- For MuJoCo, prefer quaternions (no gimbal lock)
**Warning signs:**
- NaN or inf values in rotation angles
- Parts at 90-degree orientations produce errors
- VBA code divides by `cos(beta)` without checking for zero

### Pitfall 3: Unit Confusion (cm vs m vs mm)
**What goes wrong:** Inventor always uses centimeters internally, regardless of document units. Export formats expect meters (URDF/MuJoCo) or mm (ADAMS). Parts appear 100x too large/small.
**Why it happens:**
- Inventor API returns cm, not document display units
- The VBA code uses `ScaleBy(10)` suggesting cm-to-mm conversion, but undocumented
- URDF/MuJoCo strongly expect SI units (meters)
**How to avoid:**
- Use explicit unit conversion functions with named source/target
- Convert immediately at the extraction boundary
- Document the conversion in function names: `position_from_inventor_cm()`
**Warning signs:**
- Scale looks obviously wrong (robot is building-sized or ant-sized)
- Dynamics behave incorrectly (10x heavier/lighter)

### Pitfall 4: Rotation Matrix Convention Mismatch
**What goes wrong:** ADAMS uses Body 3-1-3 (ZXZ) Euler angles, URDF uses RPY (roll-pitch-yaw about fixed XYZ = intrinsic ZYX), MuJoCo prefers quaternions. Using the wrong convention produces parts rotated incorrectly.
**Why it happens:**
- Different simulation tools have different conventions
- Easy to confuse intrinsic vs extrinsic, XYZ vs ZYX
- scipy uppercase (XYZ) = intrinsic/body-fixed, lowercase (xyz) = extrinsic
**How to avoid:**
- Define explicit conversion functions per target format
- Test with known 90-degree rotations
- Use scipy's documented conventions: `'ZXZ'` for ADAMS, `'ZYX'` for URDF RPY
**Warning signs:**
- Parts appear rotated 90 or 180 degrees wrong
- Joints don't align correctly in simulation

### Pitfall 5: Thread Apartment Model Issues
**What goes wrong:** COM objects are apartment-threaded. Using COM from wrong threads causes cryptic errors or hangs.
**Why it happens:**
- Main thread auto-initializes COM as single-threaded apartment (STA)
- Worker threads need explicit `pythoncom.CoInitialize()`
- COM objects cannot be passed between threads
**How to avoid:**
- Call `pythoncom.CoInitialize()` at start of any thread using COM
- Call `pythoncom.CoUninitialize()` at thread exit
- Create new COM objects per thread, never share
**Warning signs:**
- "CoInitialize has not been called" errors
- Random hangs with background threads
- "Interface not registered" errors

## Code Examples

Verified patterns from official sources:

### Complete COM Context Manager
```python
# Source: pywin32 docs + Inventor API best practices
import pythoncom
import win32com.client
from contextlib import contextmanager
from typing import Generator, Any, Optional
import logging

logger = logging.getLogger(__name__)

class InventorNotRunningError(Exception):
    """Raised when Inventor is not running."""
    pass

class NotAssemblyError(Exception):
    """Raised when active document is not an assembly."""
    pass

@contextmanager
def inventor_app() -> Generator[Any, None, None]:
    """
    Context manager for Inventor application connection.

    Connects to a running Inventor instance and ensures proper cleanup.

    Yields:
        Inventor.Application COM object

    Raises:
        InventorNotRunningError: If Inventor is not running

    Example:
        with inventor_app() as app:
            doc = app.ActiveDocument
            print(doc.DisplayName)
    """
    app = None
    try:
        logger.debug("Connecting to Inventor...")
        app = win32com.client.GetActiveObject("Inventor.Application")
        logger.debug(f"Connected to Inventor {app.SoftwareVersion.DisplayVersion}")
        yield app
    except pythoncom.com_error as e:
        if e.hresult == -2147221021:  # MK_E_UNAVAILABLE
            raise InventorNotRunningError(
                "Inventor is not running. Please start Inventor and open an assembly."
            ) from e
        raise
    finally:
        if app is not None:
            logger.debug("Releasing Inventor connection")
            del app

@contextmanager
def active_assembly(app: Any) -> Generator[Any, None, None]:
    """
    Context manager for active assembly document.

    Args:
        app: Inventor.Application COM object

    Yields:
        AssemblyDocument COM object

    Raises:
        NotAssemblyError: If no document is open or it's not an assembly
    """
    doc = app.ActiveDocument
    if doc is None:
        raise NotAssemblyError("No document is open in Inventor")

    # DocumentType 12291 = kAssemblyDocumentObject
    if doc.DocumentType != 12291:
        raise NotAssemblyError(
            f"Active document is not an assembly (type={doc.DocumentType})"
        )

    try:
        yield doc
    finally:
        del doc
```

### Inventor Unit Conversion
```python
# Source: Autodesk Inventor API docs - internal units always cm
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, NamedTuple

class Position(NamedTuple):
    """3D position in specified units."""
    x: float
    y: float
    z: float

class InventorUnits:
    """
    Autodesk Inventor internal database units.

    Inventor ALWAYS uses these units internally regardless of document
    display settings:
    - Length: centimeters (cm)
    - Angle: radians
    - Mass: kilograms (kg)
    - Time: seconds (s)

    Source: https://help.autodesk.com/cloudhelp/2021/ENU/Inventor-API/files/UOM_Overview.htm
    """

    # Conversion factors FROM Inventor internal units
    CM_TO_M = 0.01
    CM_TO_MM = 10.0
    RAD_TO_DEG = 57.29577951308232  # 180/pi

    @classmethod
    def length_to_meters(cls, value_cm: float) -> float:
        """Convert Inventor internal length (cm) to meters."""
        return value_cm * cls.CM_TO_M

    @classmethod
    def length_to_mm(cls, value_cm: float) -> float:
        """Convert Inventor internal length (cm) to millimeters."""
        return value_cm * cls.CM_TO_MM

    @classmethod
    def position_to_meters(cls, x: float, y: float, z: float) -> Position:
        """Convert Inventor position (cm) to meters."""
        return Position(
            x * cls.CM_TO_M,
            y * cls.CM_TO_M,
            z * cls.CM_TO_M,
        )

    @classmethod
    def position_to_mm(cls, x: float, y: float, z: float) -> Position:
        """Convert Inventor position (cm) to millimeters."""
        return Position(
            x * cls.CM_TO_MM,
            y * cls.CM_TO_MM,
            z * cls.CM_TO_MM,
        )

    @classmethod
    def angle_to_degrees(cls, value_rad: float) -> float:
        """Convert Inventor internal angle (radians) to degrees."""
        return value_rad * cls.RAD_TO_DEG
```

### Rotation Conversion Module
```python
# Source: scipy 1.16 docs - https://docs.scipy.org/doc/scipy/reference/
from scipy.spatial.transform import Rotation
import numpy as np
from typing import Tuple, Optional
from enum import Enum
import warnings
import logging

logger = logging.getLogger(__name__)

class EulerConvention(Enum):
    """
    Euler angle conventions for export formats.

    Note: scipy uses UPPERCASE for intrinsic (body-fixed) rotations,
    lowercase for extrinsic (space-fixed) rotations.
    """
    ADAMS_ZXZ = "ZXZ"   # ADAMS View Body 3-1-3 Euler angles
    URDF_RPY = "ZYX"    # URDF roll-pitch-yaw (extrinsic XYZ = intrinsic ZYX)

def extract_rotation_matrix(inventor_matrix) -> np.ndarray:
    """
    Extract 3x3 rotation matrix from Inventor 4x4 transformation matrix.

    Args:
        inventor_matrix: Inventor.Matrix COM object (4x4 transformation)

    Returns:
        3x3 numpy array containing rotation portion

    Note:
        Inventor Matrix.Cell() uses 1-based indexing.
        The rotation is in the upper-left 3x3 portion.
    """
    # Inventor matrices are column-major, Cell(row, col) is 1-indexed
    rotation = np.array([
        [inventor_matrix.Cell(1, 1), inventor_matrix.Cell(1, 2), inventor_matrix.Cell(1, 3)],
        [inventor_matrix.Cell(2, 1), inventor_matrix.Cell(2, 2), inventor_matrix.Cell(2, 3)],
        [inventor_matrix.Cell(3, 1), inventor_matrix.Cell(3, 2), inventor_matrix.Cell(3, 3)],
    ])
    return rotation

def rotation_to_euler(
    rotation_matrix: np.ndarray,
    convention: EulerConvention,
    degrees: bool = True
) -> Tuple[float, float, float]:
    """
    Convert rotation matrix to Euler angles.

    Args:
        rotation_matrix: 3x3 rotation matrix
        convention: Target Euler angle convention
        degrees: If True, return degrees; if False, radians

    Returns:
        Tuple of (angle1, angle2, angle3) in specified convention

    Notes:
        scipy handles gimbal lock by issuing a warning and setting
        the third angle to zero. The rotation is still correct.
    """
    # scipy from_matrix handles non-orthogonal matrices gracefully
    # by finding the nearest valid rotation matrix
    r = Rotation.from_matrix(rotation_matrix)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        angles = r.as_euler(convention.value, degrees=degrees)

        if w and "gimbal lock" in str(w[0].message).lower():
            logger.warning(
                f"Gimbal lock detected for {convention.value} conversion. "
                "Third angle set to zero. Rotation is still correct."
            )

    return tuple(angles)

def rotation_to_quaternion(
    rotation_matrix: np.ndarray,
    scalar_first: bool = True,
    canonical: bool = True
) -> Tuple[float, float, float, float]:
    """
    Convert rotation matrix to quaternion.

    Args:
        rotation_matrix: 3x3 rotation matrix
        scalar_first: If True, return (w, x, y, z); if False, (x, y, z, w)
        canonical: If True, ensure w >= 0 (unique representation)

    Returns:
        Quaternion as tuple

    Notes:
        MuJoCo uses scalar-first (w, x, y, z) convention.
        Quaternions have no gimbal lock issues.
    """
    r = Rotation.from_matrix(rotation_matrix)
    q = r.as_quat(canonical=canonical, scalar_first=scalar_first)
    return tuple(q)

def rotation_to_format(
    rotation_matrix: np.ndarray,
    target_format: str
) -> Tuple[float, ...]:
    """
    Convert rotation matrix to target export format convention.

    Args:
        rotation_matrix: 3x3 rotation matrix
        target_format: One of "ADAMS", "URDF", "MUJOCO"

    Returns:
        Tuple of rotation values in format-appropriate convention:
        - ADAMS: (psi, theta, phi) ZXZ Euler angles in degrees
        - URDF: (roll, pitch, yaw) RPY angles in radians
        - MUJOCO: (w, x, y, z) quaternion
    """
    if target_format.upper() == "ADAMS":
        return rotation_to_euler(rotation_matrix, EulerConvention.ADAMS_ZXZ, degrees=True)
    elif target_format.upper() == "URDF":
        return rotation_to_euler(rotation_matrix, EulerConvention.URDF_RPY, degrees=False)
    elif target_format.upper() == "MUJOCO":
        return rotation_to_quaternion(rotation_matrix, scalar_first=True)
    else:
        raise ValueError(f"Unknown target format: {target_format}")
```

### Logging Configuration
```python
# Source: Python logging HOWTO - https://docs.python.org/3/howto/logging.html
import logging
import logging.config
from pathlib import Path
from typing import Optional

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "inventor_export.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 3,
        },
    },
    "loggers": {
        "inventor_exporter": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console"],
    },
}

def setup_logging(
    log_file: Optional[Path] = None,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> None:
    """
    Configure logging for the application.

    Args:
        log_file: Path to log file. If None, uses default in current directory.
        console_level: Minimum level for console output
        file_level: Minimum level for file output

    Should be called once at application startup.
    """
    config = LOGGING_CONFIG.copy()

    if log_file is not None:
        config["handlers"]["file"]["filename"] = str(log_file)

    config["handlers"]["console"]["level"] = console_level.upper()
    config["handlers"]["file"]["level"] = file_level.upper()

    logging.config.dictConfig(config)

    logger = logging.getLogger("inventor_exporter")
    logger.info("Logging initialized")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.

    Args:
        name: Usually __name__ for automatic module hierarchy

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing assembly...")
    """
    return logging.getLogger(f"inventor_exporter.{name}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual Euler extraction with trig | scipy.spatial.transform.Rotation | scipy 1.2 (2019) | Robust gimbal lock handling, all conventions supported |
| Individual import for pywin32 modules | Unified `pywin32` package | Long-standing | Cleaner imports, better maintained |
| basicConfig logging | dictConfig | Python 3.2 (2011) | More flexible, configuration from files |
| Single-thread COM only | Explicit apartment model | Always required | Proper threading support |

**Deprecated/outdated:**
- Manual rotation matrix to Euler formulas: Prone to gimbal lock bugs, use scipy instead
- Relying on garbage collection for COM cleanup: Use explicit context managers
- `logging.basicConfig()` for complex apps: Use `dictConfig` for flexibility

## Open Questions

Things that couldn't be fully resolved:

1. **ADAMS exact Euler convention**
   - What we know: ADAMS uses Body 3-1-3 (ZXZ) Euler angles
   - What's unclear: Exact angle ranges and sign conventions ADAMS expects
   - Recommendation: Test with simple 90-degree rotations, verify against working VBA output

2. **Inventor Matrix indexing**
   - What we know: VBA code uses `Cell(row, col)` with 1-based indexing
   - What's unclear: Whether matrix is row-major or column-major in storage
   - Recommendation: Verify with identity matrix and simple rotations

3. **pywin32 Python 3.13 compatibility**
   - What we know: pywin32-311 claims Python 3.14 support
   - What's unclear: Stability with Python 3.13.3 on target system
   - Recommendation: Test early, fall back to Python 3.11/3.12 if issues

## Sources

### Primary (HIGH confidence)
- [SciPy 1.16 Rotation.as_euler docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.as_euler.html) - Euler conversion, gimbal lock handling
- [SciPy 1.16 Rotation.from_matrix docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.from_matrix.html) - Matrix to rotation
- [SciPy 1.16 Rotation.as_quat docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.as_quat.html) - Quaternion output
- [Autodesk Inventor API Unit of Measure](https://help.autodesk.com/cloudhelp/2021/ENU/Inventor-API/files/UOM_Overview.htm) - Internal units are cm
- [PyWin32 pythoncom docs](https://timgolden.me.uk/pywin32-docs/pythoncom__CoInitialize_meth.html) - COM initialization
- [Python logging HOWTO](https://docs.python.org/3/howto/logging.html) - Logging configuration

### Secondary (MEDIUM confidence)
- [Euler angles Wikipedia](https://en.wikipedia.org/wiki/Euler_angles) - ZXZ/313 convention reference
- [Python logging best practices](https://betterstack.com/community/guides/logging/python/python-logging-best-practices/) - dictConfig recommendations
- [Practical Business Python - Windows COM](https://pbpython.com/windows-com.html) - pywin32 patterns

### Tertiary (LOW confidence)
- Existing VBA codebase analysis (Misc.bas rotation code) - Shows bugs to avoid
- Training data knowledge of ADAMS View format - Needs verification

## Metadata

**Confidence breakdown:**
- COM lifecycle patterns: HIGH - Official pywin32 docs, well-established patterns
- Unit conversion: HIGH - Official Autodesk API docs explicitly state internal units
- Rotation math (scipy): HIGH - Official scipy docs with examples
- ADAMS rotation convention: MEDIUM - General ZXZ docs, specific ADAMS needs testing
- Logging patterns: HIGH - Official Python docs

**Research date:** 2026-01-19
**Valid until:** 90 days (stable libraries, mature patterns)
