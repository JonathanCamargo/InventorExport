# Domain Pitfalls

**Domain:** CAD-to-Simulation Export Tools (Python COM Automation + Autodesk Inventor)
**Researched:** 2026-01-19

## Critical Pitfalls

Mistakes that cause rewrites, corrupt exports, or produce physically incorrect simulations.

### Pitfall 1: COM Object Lifetime Mismanagement

**What goes wrong:** Python COM objects (via pywin32) hold references to Inventor objects. If not properly released, Inventor accumulates unreleased COM references, leading to memory leaks, slowdowns, and eventual crashes. Worse, some operations silently fail when stale references are used.

**Why it happens:**
- Python's garbage collector doesn't deterministically release COM objects
- Caching COM objects for "performance" creates stale references when Inventor state changes
- Exception handlers that don't clean up COM references
- Storing COM collections when iterating (the collection may change)

**Consequences:**
- Inventor becomes unresponsive after multiple exports
- Silent data corruption when stale references return outdated values
- "Automation error" exceptions that are difficult to debug
- Inventor process cannot close cleanly

**Prevention:**
```python
# BAD: Implicit cleanup
def export_parts():
    app = win32com.client.Dispatch("Inventor.Application")
    doc = app.ActiveDocument
    for part in doc.AllReferencedDocuments:
        process(part)
    # References leak when function exits via exception

# GOOD: Explicit cleanup with context managers
import contextlib

@contextlib.contextmanager
def inventor_session():
    app = win32com.client.Dispatch("Inventor.Application")
    try:
        yield app
    finally:
        # Release in reverse order of acquisition
        del app
        # Force COM release
        import gc
        gc.collect()
        pythoncom.CoUninitialize()
```

**Detection:**
- Inventor's Task Manager memory grows with each export
- "RPC server is unavailable" errors after extended use
- Inventor hangs on close
- Sporadic "Object disconnected" exceptions

**Phase to address:** Core/Infrastructure phase - must establish COM lifecycle patterns before any feature work.

---

### Pitfall 2: Euler Angle Gimbal Lock and Rotation Order Mismatch

**What goes wrong:** Euler angle extraction from rotation matrices has mathematical singularities (gimbal lock) and requires matching rotation order between source (Inventor) and target (ADAMS/URDF/MuJoCo). Using the wrong convention produces parts rotated incorrectly in simulation.

**Why it happens:**
- Inventor uses a specific rotation order (likely XYZ or ZYX intrinsic)
- ADAMS View uses Body 3-1-3 Euler angles by default
- URDF uses RPY (Roll-Pitch-Yaw, which is XYZ extrinsic = ZYX intrinsic)
- MuJoCo uses quaternions or axis-angle
- The existing VBA code has a division-by-zero bug near gimbal lock (when cos(beta) = 0)

**Consequences:**
- Parts appear rotated 90/180 degrees wrong in simulation
- Gimbal lock causes NaN or division-by-zero errors
- Simulation joints don't align correctly
- Model "explodes" on simulation start due to misaligned parts

**Prevention:**
```python
# Use scipy.spatial.transform for robust rotation handling
from scipy.spatial.transform import Rotation

def matrix_to_euler(inventor_matrix, target_convention='ZYX'):
    """Convert Inventor transformation matrix to target Euler convention."""
    # Extract 3x3 rotation from 4x4 transformation
    rot_matrix = extract_rotation_3x3(inventor_matrix)

    r = Rotation.from_matrix(rot_matrix)

    # Convert to target convention - scipy handles gimbal lock
    if target_convention == 'ADAMS':
        # ADAMS uses Body 3-1-3 (ZXZ)
        return r.as_euler('zxz', degrees=True)
    elif target_convention == 'URDF':
        # URDF uses RPY (roll-pitch-yaw about fixed XYZ = intrinsic ZYX)
        return r.as_euler('ZYX', degrees=False)
    elif target_convention == 'MUJOCO':
        # MuJoCo prefers quaternions
        return r.as_quat()  # [x, y, z, w]
```

**Detection:**
- Visual inspection shows parts rotated incorrectly
- Unit tests with known 90-degree rotations fail
- Parts at ~90 degree orientations produce NaN or inf values

**Phase to address:** Data Model phase - rotation handling is foundational to all format exports.

---

### Pitfall 3: Coordinate System Origin and Scale Mismatch

**What goes wrong:** CAD software and simulation software often use different:
- Units (mm vs m vs cm)
- Coordinate origins (world vs part vs assembly origin)
- Axis conventions (Y-up vs Z-up)

**Why it happens:**
- Inventor defaults to mm or cm depending on template
- ADAMS can be configured for various unit systems
- URDF/MuJoCo strongly prefer SI units (meters)
- The VBA code uses `trans.ScaleBy(10)` suggesting a mm-to-cm conversion, but this is applied inconsistently

**Consequences:**
- Parts appear at wrong scale (1000x too big or small)
- Parts positioned meters away from where they should be
- Gravity and dynamics behave incorrectly (10x heavier/lighter)
- Joints don't connect because positions don't match

**Prevention:**
```python
class UnitConverter:
    """Centralized unit conversion with explicit source/target."""

    INVENTOR_LENGTH_UNIT = 'cm'  # Inventor internal units

    TARGET_UNITS = {
        'ADAMS': 'mm',    # ADAMS View default
        'URDF': 'm',      # ROS/URDF standard
        'MUJOCO': 'm',    # MuJoCo standard
    }

    CONVERSION = {
        ('cm', 'm'): 0.01,
        ('cm', 'mm'): 10.0,
        ('mm', 'm'): 0.001,
        # ... etc
    }

    @classmethod
    def convert_position(cls, pos, target_format):
        scale = cls.CONVERSION[(cls.INVENTOR_LENGTH_UNIT, cls.TARGET_UNITS[target_format])]
        return tuple(p * scale for p in pos)
```

**Detection:**
- Simulation shows parts at origin when they shouldn't be
- Scale looks obviously wrong (robot is building-sized or ant-sized)
- Part-to-part distances don't match CAD measurements

**Phase to address:** Data Model phase - unit handling must be defined before any export logic.

---

### Pitfall 4: Assembly Hierarchy Flattening Errors

**What goes wrong:** Inventor assemblies can have nested subassemblies. When flattening to simulation formats (which often expect flat part lists), transformation accumulation errors occur.

**Why it happens:**
- Each subassembly level has its own coordinate frame
- Part transformations must be composed (multiplied) through the hierarchy
- The order of multiplication matters (parent * child, not child * parent)
- Flexible subassemblies vs rigid subassemblies have different semantics

**Consequences:**
- Parts appear at wrong positions
- Parts from nested subassemblies are missing
- Same part appears multiple times at same location
- Pattern/mirror features produce incorrect instances

**Prevention:**
```python
def collect_leaf_occurrences(assembly_def):
    """Recursively collect all leaf parts with accumulated transforms."""
    results = []

    def recurse(occurrence, accumulated_transform):
        if is_part(occurrence):
            # Leaf part - combine transforms
            world_transform = accumulated_transform @ occurrence.Transformation
            results.append((occurrence, world_transform))
        else:
            # Subassembly - recurse with combined transform
            for child in occurrence.SubOccurrences:
                new_transform = accumulated_transform @ occurrence.Transformation
                recurse(child, new_transform)

    # Start with identity
    for top_level in assembly_def.Occurrences:
        recurse(top_level, identity_matrix())

    return results
```

**Detection:**
- Part count in export differs from Inventor BOM
- Parts from subassemblies have wrong positions
- Some instances of patterned parts are missing

**Phase to address:** Extraction phase - hierarchy traversal must be correct before any format output.

---

### Pitfall 5: STEP Export Geometry Mismatch

**What goes wrong:** STEP files exported from Inventor may not match the visual appearance in CAD due to tessellation settings, suppressed features, or coordinate frame differences.

**Why it happens:**
- STEP translator has options (AP203 vs AP214) that affect what's exported
- Part-level coordinate system differs from occurrence-level placement
- Inventor applies visual simplification that isn't in the STEP
- Some features (sheet metal bends, adaptive parts) export differently

**Consequences:**
- Geometry appears different in simulation viewer
- Parts don't mate correctly when imported to simulation
- Collision geometry doesn't match visual geometry
- File sizes are unexpectedly large or small

**Prevention:**
```python
def export_to_step(part_doc, output_path, options=None):
    """Export with explicit options and validation."""
    if options is None:
        options = {
            'ApplicationProtocolType': 3,  # AP214 for better compatibility
            'ExportFaceColors': True,
            'ExportBSplineSurfaces': True,
        }

    # Validate part is fully resolved
    if part_doc.IsModifiable == False:
        raise ExportError(f"Part {part_doc.DisplayName} is not editable")

    # Check for suppressed features that might affect export
    for feature in part_doc.ComponentDefinition.Features:
        if feature.Suppressed:
            log.warning(f"Suppressed feature: {feature.Name}")

    # Export with explicit options
    translator = get_step_translator(app)
    # ... export logic
```

**Detection:**
- Visual comparison between Inventor and simulation viewer
- Bounding box size doesn't match expected dimensions
- STEP file is unexpectedly small (missing geometry)

**Phase to address:** Export phase - but foundational patterns in Core.

---

## Moderate Pitfalls

Mistakes that cause delays, debugging time, or technical debt.

### Pitfall 6: pythoncom Thread Apartment Model Issues

**What goes wrong:** COM objects are apartment-threaded. Using COM objects from wrong threads causes cryptic errors or hangs.

**Why it happens:**
- Python's default is STA (Single-Threaded Apartment)
- Background threads need `pythoncom.CoInitialize()`
- Passing COM objects between threads is prohibited
- Async code patterns conflict with COM threading

**Prevention:**
```python
import pythoncom
import threading

def worker_thread():
    # MUST initialize COM in each thread
    pythoncom.CoInitialize()
    try:
        # Create NEW COM objects - don't share from main thread
        app = win32com.client.Dispatch("Inventor.Application")
        # ... work
    finally:
        pythoncom.CoUninitialize()
```

**Detection:**
- "CoInitialize has not been called" errors
- Hangs when using COM from background threads
- Random "Interface not registered" errors

**Phase to address:** Core/Infrastructure phase.

---

### Pitfall 7: Material Property Extraction Complexity

**What goes wrong:** Inventor material properties are stored in a complex asset system. Simple property access returns wrong values or fails.

**Why it happens:**
- Materials have "appearance" assets and "physical" assets
- Property values have different schemas per material type
- Some properties are calculated, not stored
- Library materials vs document materials have different access patterns

**Prevention:**
```python
def get_material_properties(part_doc):
    """Extract physical material properties robustly."""
    material = part_doc.ActiveMaterial

    # Physical properties are in a separate asset
    physical_asset = material.PhysicalPropertiesAsset

    if physical_asset is None:
        # Material doesn't have physical properties defined
        return default_material_properties()

    properties = {}

    # Access properties by their schema names
    for prop_name in ['Density', 'YoungsModulus', 'PoissonsRatio']:
        try:
            prop = physical_asset.Item(prop_name)
            if prop is not None:
                properties[prop_name] = prop.Value
        except:
            log.warning(f"Missing property: {prop_name}")
            properties[prop_name] = None

    return properties
```

**Detection:**
- All materials return same values
- Certain materials throw exceptions
- Values are obviously wrong (density of 0, etc.)

**Phase to address:** Extraction phase.

---

### Pitfall 8: File Path Encoding and Special Characters

**What goes wrong:** Component names from Inventor can contain characters illegal in file paths or problematic for simulation file formats.

**Why it happens:**
- Inventor allows unicode characters in part names
- Some characters are reserved in Windows paths (: * ? " < > |)
- ADAMS/URDF have restrictions on identifier characters
- Colons appear naturally in Inventor occurrence names (Part:1, Part:2)

**Prevention:**
```python
import re

def sanitize_name(inventor_name: str, target_format: str) -> str:
    """Sanitize Inventor names for target format compatibility."""

    # Replace Inventor occurrence separators
    name = inventor_name.replace(':', '_')

    # Remove/replace illegal filesystem characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)

    # Format-specific restrictions
    if target_format == 'URDF':
        # URDF names must be valid XML NCName
        name = re.sub(r'^[^a-zA-Z_]', '_', name)  # Must start with letter or _
        name = re.sub(r'[^a-zA-Z0-9_.-]', '_', name)

    elif target_format == 'ADAMS':
        # ADAMS names: alphanumeric and underscore only
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)

    return name
```

**Detection:**
- Export fails with "invalid path" errors
- Target software rejects the file as malformed
- Name collisions after sanitization

**Phase to address:** Core utilities - needed by all format writers.

---

### Pitfall 9: Inertia Tensor Reference Frame Confusion

**What goes wrong:** Mass properties (center of mass, inertia tensor) are reported in different reference frames. Using them without transformation produces incorrect dynamics.

**Why it happens:**
- Inventor reports inertia at part origin, not center of mass
- Some formats want inertia at CoM, others at link origin
- Principal axes of inertia may not align with part axes
- Inertia is a tensor that transforms differently than vectors

**Prevention:**
```python
import numpy as np

def transform_inertia_tensor(I_local, R, m, d):
    """
    Transform inertia tensor to new frame.

    I_local: 3x3 inertia tensor in local frame
    R: 3x3 rotation matrix from local to new frame
    m: mass
    d: displacement vector from local to new origin

    Uses parallel axis theorem: I_new = R @ I_local @ R.T + m * (d.d*eye - d@d.T)
    """
    # Rotate inertia tensor
    I_rotated = R @ I_local @ R.T

    # Apply parallel axis theorem for translation
    d = np.array(d)
    parallel_axis = m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))

    return I_rotated + parallel_axis
```

**Detection:**
- Simulation dynamics look wrong (wobbling, unexpected rotations)
- Inertia values are negative (impossible)
- Order of magnitude doesn't match expected values

**Phase to address:** Data Model phase - fundamental to physics-based export.

---

### Pitfall 10: ADAMS View Command Syntax Versioning

**What goes wrong:** ADAMS View command file syntax varies between versions. Generated files may not load in different ADAMS versions.

**Why it happens:**
- ADAMS View evolves its command language
- Some commands are deprecated or renamed
- Required parameters change between versions
- The existing VBA code targets one specific version

**Prevention:**
```python
class AdamsWriter:
    """Version-aware ADAMS View writer."""

    SUPPORTED_VERSIONS = ['2019', '2020', '2021', '2022']

    def __init__(self, version='2022'):
        if version not in self.SUPPORTED_VERSIONS:
            raise ValueError(f"Unsupported ADAMS version: {version}")
        self.version = version
        self.syntax = self._load_syntax(version)

    def write_material(self, name, properties):
        """Write material with version-appropriate syntax."""
        template = self.syntax['material_create']
        return template.format(
            name=name,
            density=properties['density'],
            youngs=properties['youngs_modulus'],
            # ...
        )
```

**Detection:**
- ADAMS reports syntax errors on file load
- Certain commands are "not recognized"
- Model loads but properties are missing

**Phase to address:** Format Writers phase.

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable without major rework.

### Pitfall 11: Debug Output Pollution

**What goes wrong:** Excessive Debug.Print (VBA) or print() (Python) statements make it hard to find actual errors.

**Prevention:** Use proper logging with levels:
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('inventor_export')

logger.debug("Processing part: %s", part_name)  # Only in debug mode
logger.info("Exported %d parts", count)          # Normal operation
logger.warning("Missing material, using default") # Potential issues
logger.error("STEP export failed: %s", error)     # Failures
```

**Phase to address:** Core infrastructure.

---

### Pitfall 12: Missing EXPORT Folder

**What goes wrong:** Export fails because target directory doesn't exist.

**Prevention:**
```python
from pathlib import Path

def ensure_export_dir(workspace_path):
    export_dir = Path(workspace_path) / 'EXPORT'
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir
```

**Phase to address:** Core utilities.

---

### Pitfall 13: File Handle Leaks on Exceptions

**What goes wrong:** Files remain locked if exceptions occur during write.

**Prevention:**
```python
# BAD
f = open(path, 'w')
f.write(content)  # Exception here leaves file locked
f.close()

# GOOD
with open(path, 'w') as f:
    f.write(content)  # Automatically closed even on exception
```

**Phase to address:** All phases - use context managers everywhere.

---

### Pitfall 14: Hardcoded GUIDs for Inventor Add-Ins

**What goes wrong:** Add-In GUIDs like the STEP translator ID may change between Inventor versions.

**Prevention:**
```python
def find_step_translator(app):
    """Find STEP translator by name, not GUID."""
    for addin in app.ApplicationAddIns:
        if 'STEP' in addin.DisplayName.upper():
            return addin
    raise TranslatorNotFoundError("STEP translator not available")
```

**Phase to address:** Extraction/Export phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Core Infrastructure | COM lifetime management (#1), Threading (#6) | Establish COM context managers first, test lifecycle |
| Data Model | Rotation conventions (#2), Units (#3), Inertia frames (#9) | Define conversion utilities with extensive unit tests |
| Inventor Extraction | Hierarchy traversal (#4), Material properties (#7) | Test with complex nested assemblies |
| STEP Export | Geometry mismatch (#5), File paths (#8) | Visual validation pipeline |
| ADAMS Writer | Syntax versioning (#10), Path sanitization (#8) | Version detection, input validation |
| URDF Writer | Rotation order (ZYX/#2), Units (meters/#3) | Follow REP-103 conventions exactly |
| MuJoCo Writer | Quaternions (#2), Inertia at CoM (#9) | scipy Rotation for quaternion math |

## Sources

- Analysis of existing VBA codebase in repository (Main.bas, Export.bas, Misc.bas)
- Documented concerns in `.planning/codebase/CONCERNS.md`
- Training data knowledge of pywin32 COM automation patterns
- Training data knowledge of URDF, MuJoCo, and ADAMS file formats
- Training data knowledge of rigid body dynamics and coordinate transformations

**Confidence Levels:**
- COM automation pitfalls (#1, #6): MEDIUM - Based on training data, not verified against current pywin32 docs
- Rotation/coordinate pitfalls (#2, #3, #9): HIGH - Mathematical facts that don't change
- Inventor-specific pitfalls (#4, #5, #7): MEDIUM - Based on VBA code analysis and training data
- Format-specific pitfalls (#10): MEDIUM - Based on training data, should verify against current format specifications

---

*Pitfalls research: 2026-01-19*
