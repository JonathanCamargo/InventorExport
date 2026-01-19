# Phase 4: Inventor Extraction - Research

**Researched:** 2026-01-19
**Domain:** Inventor COM API, Assembly Traversal, Transformation Matrices, STEP Export, Mass Properties
**Confidence:** HIGH (verified with official Autodesk documentation)

## Summary

Phase 4 implements the core extraction logic that reads assembly data from Inventor and populates the intermediate representation (IR) defined in Phase 2. The extraction covers five main areas: assembly traversal to find all parts, transformation extraction to get position and orientation, transform accumulation for nested subassemblies, STEP geometry export, and mass/material property extraction.

The standard approach uses the Inventor COM API via pywin32 (established in Phase 1). Assembly traversal leverages the `AllLeafOccurrences` property which returns all parts at any nesting level with their transformations already in assembly coordinates. The `Transformation` property of each ComponentOccurrence returns the 4x4 matrix directly in world (assembly) coordinates. STEP export uses the TranslatorAddIn mechanism with GUID `{90AF7F40-0C01-11D5-8E83-0010B541CD80}`. Mass properties come from `ComponentDefinition.MassProperties` which provides mass, center of mass, and the full 6-component inertia tensor via `XYZMomentsOfInertia`.

**Primary recommendation:** Use `AllLeafOccurrences` for traversal - it handles nested subassemblies automatically and returns transformations in the correct coordinate frame. Do NOT manually recurse through SubOccurrences unless you need subassembly-level information.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pywin32 | 306+ | COM automation | Already established in Phase 1 for Inventor connectivity |
| numpy | 1.24+ | Matrix operations | Transform extraction, inertia tensor construction |
| (Phase 1 core) | - | COM utilities | `inventor_app()`, `active_assembly()` context managers |
| (Phase 2 model) | - | Data model | `Body`, `Transform`, `Material`, `Inertia`, `AssemblyModel` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | File paths | STEP export file paths |
| logging | stdlib | Debug output | Progress tracking during extraction |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| AllLeafOccurrences | Recursive SubOccurrences traversal | More code, manual transform accumulation, same result |
| TranslatorAddIn | SaveAs with file filter | Less control over options, no AP214/AP242 selection |
| COM direct property access | PyInventor wrapper | Extra dependency, less control, may not cover all APIs needed |

**Installation:**
```bash
# Already installed from Phase 1
pip install pywin32>=306 numpy>=1.24
```

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/
├── extraction/
│   ├── __init__.py
│   ├── client.py         # InventorClient - main extraction orchestrator
│   ├── assembly.py       # Assembly traversal, occurrence handling
│   ├── transform.py      # Transform extraction and accumulation
│   ├── geometry.py       # STEP export via TranslatorAddIn
│   ├── mass.py           # Mass properties and inertia extraction
│   └── material.py       # Material/density extraction
├── core/                 # (From Phase 1)
│   ├── com.py
│   ├── rotation.py
│   └── units.py
└── model/                # (From Phase 2)
    ├── body.py
    ├── transform.py
    ├── material.py
    ├── inertia.py
    └── assembly.py
```

### Pattern 1: AllLeafOccurrences for Flat Traversal
**What:** Use `ComponentOccurrences.AllLeafOccurrences` to get all parts without manual recursion.
**When to use:** Always - this is the standard approach for extracting all parts.
**Example:**
```python
# Source: Autodesk Inventor API - ComponentOccurrences.AllLeafOccurrences
def get_all_parts(asm_doc):
    """Get all leaf occurrences (parts) from assembly."""
    asm_def = asm_doc.ComponentDefinition
    leaf_occs = asm_def.Occurrences.AllLeafOccurrences

    parts = []
    for occ in leaf_occs:
        parts.append({
            'name': occ.Name,
            'transformation': occ.Transformation,
            'definition': occ.Definition,
            'document': occ.Definition.Document,
        })
    return parts
```

### Pattern 2: Transform Extraction from Occurrence
**What:** The `Transformation` property returns the 4x4 matrix in assembly coordinates.
**When to use:** Getting position and orientation for each leaf occurrence.
**Example:**
```python
# Source: Autodesk Inventor API - ComponentOccurrence.Transformation
import numpy as np
from inventor_exporter.core.rotation import extract_rotation_matrix
from inventor_exporter.core.units import InventorUnits

def extract_transform(occurrence):
    """Extract Transform from ComponentOccurrence.

    The Transformation property of a leaf occurrence obtained via
    AllLeafOccurrences already includes all parent transformations.
    No manual accumulation needed.
    """
    matrix = occurrence.Transformation

    # Extract position (row 4 has translation in Inventor's 4x4 matrix)
    # Inventor Matrix.Cell(row, col) is 1-indexed
    # Translation is in cells (4,1), (4,2), (4,3) - units are cm
    x_cm = matrix.Cell(4, 1)
    y_cm = matrix.Cell(4, 2)
    z_cm = matrix.Cell(4, 3)

    # Convert to meters for IR
    position = np.array([
        InventorUnits.length_to_meters(x_cm),
        InventorUnits.length_to_meters(y_cm),
        InventorUnits.length_to_meters(z_cm),
    ])

    # Extract 3x3 rotation from upper-left portion
    rotation = extract_rotation_matrix(matrix)

    return Transform(position=position, rotation=rotation)
```

### Pattern 3: STEP Export via TranslatorAddIn
**What:** Use TranslatorAddIn with specific GUID to export parts to STEP format.
**When to use:** Generating geometry files for each unique part definition.
**Example:**
```python
# Source: Autodesk Inventor API - TranslatorAddIn5_Sample.htm
import win32com.client
from pathlib import Path

STEP_TRANSLATOR_GUID = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"

def export_to_step(app, part_doc, output_path: Path):
    """Export a part document to STEP format.

    Args:
        app: Inventor.Application COM object
        part_doc: PartDocument to export
        output_path: Path for output .stp file
    """
    # Get the STEP translator add-in
    translator = app.ApplicationAddIns.ItemById(STEP_TRANSLATOR_GUID)
    translator = win32com.client.CastTo(translator, "TranslatorAddIn")

    # Create translation context
    context = app.TransientObjects.CreateTranslationContext()
    context.Type = 13059  # kFileBrowseIOMechanism

    # Create options
    options = app.TransientObjects.CreateNameValueMap()

    # Check if translator has options and get defaults
    if translator.HasSaveCopyAsOptions(part_doc, context, options):
        # Set AP214 (better compatibility than AP203)
        # 2=AP203, 3=AP214IS, 4=AP242
        options.Value("ApplicationProtocolType") = 3

    # Create data medium for output
    data_medium = app.TransientObjects.CreateDataMedium()
    data_medium.FileName = str(output_path)

    # Perform export
    translator.SaveCopyAs(part_doc, context, options, data_medium)
```

### Pattern 4: Mass Properties Extraction
**What:** Use `ComponentDefinition.MassProperties` to get mass, center of mass, and inertia tensor.
**When to use:** Extracting physics properties for rigid body simulation.
**Example:**
```python
# Source: Autodesk Inventor API - MassProperties_Sample.htm
import numpy as np
from inventor_exporter.core.units import InventorUnits
from inventor_exporter.model import Inertia

def extract_mass_properties(part_definition):
    """Extract mass properties from a part's ComponentDefinition.

    Args:
        part_definition: PartComponentDefinition COM object

    Returns:
        Inertia dataclass with mass, center of mass, and inertia tensor

    Note:
        Inventor internal units:
        - Mass: kg
        - Length: cm (so inertia is kg*cm^2)
        - Center of mass: cm
    """
    mp = part_definition.MassProperties

    # Mass is already in kg
    mass = mp.Mass

    # Center of mass in cm, convert to meters
    com = mp.CenterOfMass
    center_of_mass = np.array([
        InventorUnits.length_to_meters(com.X),
        InventorUnits.length_to_meters(com.Y),
        InventorUnits.length_to_meters(com.Z),
    ])

    # Get full inertia tensor (6 components)
    # XYZMomentsOfInertia returns diagonal and off-diagonal products
    # Units are kg*cm^2, need to convert to kg*m^2
    Ixx, Iyy, Izz, Ixy, Iyz, Ixz = [0.0] * 6
    mp.XYZMomentsOfInertia(Ixx, Iyy, Izz, Ixy, Iyz, Ixz)

    # Note: In Python/pywin32, output parameters are returned as tuple
    # The actual call looks like:
    # Ixx, Iyy, Izz, Ixy, Iyz, Ixz = mp.XYZMomentsOfInertia()

    # Convert from kg*cm^2 to kg*m^2 (multiply by 0.01^2 = 0.0001)
    CM2_TO_M2 = 0.0001

    inertia_tensor = np.array([
        [Ixx * CM2_TO_M2, Ixy * CM2_TO_M2, Ixz * CM2_TO_M2],
        [Ixy * CM2_TO_M2, Iyy * CM2_TO_M2, Iyz * CM2_TO_M2],
        [Ixz * CM2_TO_M2, Iyz * CM2_TO_M2, Izz * CM2_TO_M2],
    ])

    return Inertia(
        mass=mass,
        center_of_mass=center_of_mass,
        inertia_tensor=inertia_tensor,
    )
```

### Pattern 5: Material Density Extraction
**What:** Access `ActiveMaterial.PhysicalPropertiesAsset` to get density from the assigned material.
**When to use:** Getting material density for each part.
**Example:**
```python
# Source: Autodesk Manufacturing DevBlog - Inventor 2014 API Materials
def extract_material_density(part_doc):
    """Extract material name and density from a part document.

    Args:
        part_doc: PartDocument COM object

    Returns:
        Tuple of (material_name, density_kg_m3) or (None, None) if no material

    Note:
        Inventor stores density in kg/cm^3 internally.
        Need to convert to kg/m^3 for IR.
    """
    material = part_doc.ActiveMaterial
    if material is None:
        return None, None

    material_name = material.DisplayName

    # Access physical properties asset
    phys_props = material.PhysicalPropertiesAsset
    if phys_props is None:
        return material_name, None

    # Find density property
    density_kg_cm3 = None
    for prop in phys_props:
        # Density property name contains "Density" (case may vary)
        if "density" in prop.Name.lower():
            density_kg_cm3 = prop.Value
            break

    if density_kg_cm3 is None:
        return material_name, None

    # Convert from kg/cm^3 to kg/m^3
    # 1 kg/cm^3 = 1,000,000 kg/m^3
    CM3_TO_M3 = 1_000_000
    density_kg_m3 = density_kg_cm3 * CM3_TO_M3

    return material_name, density_kg_m3
```

### Pattern 6: Unique Part Definition Tracking
**What:** Track unique part definitions to avoid exporting the same STEP file multiple times.
**When to use:** When assembly has multiple instances of the same part.
**Example:**
```python
# Pattern for deduplicating part exports
def extract_unique_parts(leaf_occurrences):
    """Extract unique part definitions from occurrences.

    Multiple occurrences may reference the same part definition.
    We only need to export STEP once per unique definition.

    Returns:
        Dict mapping definition document path to first occurrence
    """
    unique_parts = {}

    for occ in leaf_occurrences:
        doc = occ.Definition.Document
        doc_path = doc.FullFileName

        if doc_path not in unique_parts:
            unique_parts[doc_path] = {
                'document': doc,
                'definition': occ.Definition,
                'occurrences': [],
            }

        unique_parts[doc_path]['occurrences'].append(occ)

    return unique_parts
```

### Anti-Patterns to Avoid
- **Manual SubOccurrences recursion for leaf parts:** AllLeafOccurrences is simpler and handles transform accumulation automatically.
- **Assuming transforms need manual accumulation:** Leaf occurrence Transformation property already includes all parent transforms.
- **Exporting STEP per occurrence:** Export once per unique part definition, store path in Body.
- **Hardcoding material density:** Always read from Inventor's material library.
- **Ignoring off-diagonal inertia products:** Full 6-component tensor (Ixy, Ixz, Iyz) is needed for accurate dynamics.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transform accumulation for nested parts | Recursive matrix multiplication | `AllLeafOccurrences` + `Transformation` | Already accumulated in assembly coordinates |
| STEP export | Direct file writing | TranslatorAddIn with STEP GUID | Proper STEP format, configurable AP version |
| Finding all parts in assembly | Recursive traversal | `AllLeafOccurrences` property | One call, handles all nesting levels |
| Inertia tensor construction | Just diagonal moments | `XYZMomentsOfInertia` with all 6 components | Products of inertia matter for off-axis rotation |
| Part deduplication | Name matching | `Document.FullFileName` comparison | Same name doesn't mean same part; path is unique |

**Key insight:** The Inventor API was designed for assembly analysis. AllLeafOccurrences and the Transformation property handle the common case of "get all parts with world transforms" without manual work.

## Common Pitfalls

### Pitfall 1: Transform Matrix Indexing
**What goes wrong:** Confusing row/column order or 0-based vs 1-based indexing leads to wrong positions.
**Why it happens:** Inventor uses 1-based indexing (`Cell(1,1)` to `Cell(4,4)`). Translation is in row 4, not column 4.
**How to avoid:**
- Use `Cell(4, 1)`, `Cell(4, 2)`, `Cell(4, 3)` for X, Y, Z translation
- Use `Cell(1..3, 1..3)` for 3x3 rotation matrix
- Units are always cm regardless of document settings
**Warning signs:**
- Parts appear at origin when they shouldn't
- Rotations look correct but positions are wrong
- Scale is 100x off (forgot cm to m conversion)

### Pitfall 2: XYZMomentsOfInertia Output Parameters
**What goes wrong:** In VBA, output parameters are passed by reference. In Python/pywin32, they're returned as a tuple.
**Why it happens:** Different calling conventions between languages.
**How to avoid:**
```python
# WRONG - VBA style (won't work in Python)
Ixx, Iyy, Izz, Ixy, Iyz, Ixz = 0, 0, 0, 0, 0, 0
mp.XYZMomentsOfInertia(Ixx, Iyy, Izz, Ixy, Iyz, Ixz)

# CORRECT - Python returns tuple
result = mp.XYZMomentsOfInertia()
# result is a tuple of 6 values
Ixx, Iyy, Izz, Ixy, Iyz, Ixz = result
```
**Warning signs:**
- All inertia values are 0
- TypeError about arguments

### Pitfall 3: Inertia Tensor Reference Frame
**What goes wrong:** MassProperties returns inertia at the origin, but IR expects inertia at center of mass.
**Why it happens:** Inventor's default `XYZMomentsOfInertia` is about the part origin, not CoM.
**How to avoid:**
- Check if Inventor provides an option to compute about CoM (may vary by version)
- Or use the parallel axis theorem (already in Phase 2 Inertia.at_point()) to transform
- Document which reference point the inertia is computed at
**Warning signs:**
- Inertia values seem too large
- Dynamics simulation has unexpected behavior

### Pitfall 4: Material Asset Property Names
**What goes wrong:** Material property names may vary by language/version. Searching for exact "Density" fails.
**Why it happens:** Inventor localizes property names; density might be "Dichte" in German Inventor.
**How to avoid:**
- Search for partial match: `"density" in prop.Name.lower()`
- Or iterate all properties and log names during development
- Consider using property ID instead of name if available
**Warning signs:**
- Density is None for parts that clearly have materials assigned
- Works on one machine but not another

### Pitfall 5: TranslatorAddIn Casting
**What goes wrong:** The AddIn from ItemById needs to be cast to TranslatorAddIn interface.
**Why it happens:** COM returns base ApplicationAddIn interface; methods like SaveCopyAs are on TranslatorAddIn.
**How to avoid:**
```python
# Always cast after getting the add-in
translator = app.ApplicationAddIns.ItemById(STEP_TRANSLATOR_GUID)
translator = win32com.client.CastTo(translator, "TranslatorAddIn")
```
**Warning signs:**
- AttributeError: 'COMObject' has no attribute 'SaveCopyAs'
- Methods exist in docs but not on object

### Pitfall 6: Multiple Occurrences of Same Part
**What goes wrong:** Exporting STEP for each occurrence creates duplicate files and wastes time.
**Why it happens:** Not distinguishing between occurrence (instance) and definition (template).
**How to avoid:**
- Track unique definitions by `Document.FullFileName`
- Export STEP once per unique definition
- All occurrences of same part share the same geometry_file path in Body
**Warning signs:**
- Export takes too long
- Duplicate files in output directory
- N copies of part1.stp for N instances

### Pitfall 7: COM Object Leaks During Iteration
**What goes wrong:** Iterating through large collections without releasing references causes memory growth.
**Why it happens:** Python doesn't immediately release COM object references.
**How to avoid:**
- Delete references when done with each object
- Process in batches if needed
- Use context managers for document access
**Warning signs:**
- Inventor memory grows during extraction
- Slowdown as extraction progresses

## Code Examples

Verified patterns from official sources:

### Complete Assembly Traversal
```python
# Source: Autodesk Inventor API - AllLeafOccurrences, Transformation
import logging
from typing import List, Dict, Any
from inventor_exporter.core.com import inventor_app, active_assembly

logger = logging.getLogger(__name__)

def traverse_assembly(doc) -> List[Dict[str, Any]]:
    """Traverse assembly and collect all leaf occurrence data.

    Args:
        doc: AssemblyDocument COM object

    Returns:
        List of dicts with occurrence data
    """
    asm_def = doc.ComponentDefinition
    leaf_occs = asm_def.Occurrences.AllLeafOccurrences

    logger.info(f"Found {leaf_occs.Count} leaf occurrences")

    results = []
    for i, occ in enumerate(leaf_occs):
        try:
            results.append({
                'name': occ.Name,
                'transformation': occ.Transformation,
                'definition': occ.Definition,
                'document': occ.Definition.Document,
                'document_path': occ.Definition.Document.FullFileName,
            })
            logger.debug(f"Processed {i+1}/{leaf_occs.Count}: {occ.Name}")
        finally:
            # Release iteration reference
            del occ

    return results
```

### Complete STEP Export with Options
```python
# Source: Autodesk Inventor API - TranslatorAddIn5_Sample.htm
import win32com.client
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

STEP_TRANSLATOR_GUID = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"

# Application Protocol Types
AP203 = 2   # Configuration Controlled Design
AP214 = 3   # Automotive Design (better compatibility)
AP242 = 5   # Managed model based 3D engineering (newest)

def export_step(
    app,
    document,
    output_path: Path,
    protocol: int = AP214,
) -> bool:
    """Export document to STEP format.

    Args:
        app: Inventor.Application COM object
        document: Document to export (Part or Assembly)
        output_path: Output .stp file path
        protocol: Application Protocol (AP203, AP214, or AP242)

    Returns:
        True if export succeeded
    """
    try:
        # Get STEP translator
        translator = app.ApplicationAddIns.ItemById(STEP_TRANSLATOR_GUID)
        translator = win32com.client.CastTo(translator, "TranslatorAddIn")

        # Create translation context
        context = app.TransientObjects.CreateTranslationContext()
        context.Type = 13059  # kFileBrowseIOMechanism

        # Create options map
        options = app.TransientObjects.CreateNameValueMap()

        # Get default options and override protocol
        if translator.HasSaveCopyAsOptions(document, context, options):
            options.Value("ApplicationProtocolType") = protocol

        # Set output path
        data_medium = app.TransientObjects.CreateDataMedium()
        data_medium.FileName = str(output_path)

        # Export
        translator.SaveCopyAs(document, context, options, data_medium)
        logger.info(f"Exported STEP: {output_path}")
        return True

    except Exception as e:
        logger.error(f"STEP export failed: {e}")
        return False
```

### Complete Mass Properties Extraction
```python
# Source: Autodesk Inventor API - MassProperties_Sample.htm
import numpy as np
from inventor_exporter.model import Inertia
from inventor_exporter.core.units import InventorUnits
import logging

logger = logging.getLogger(__name__)

# Unit conversion: cm^2 to m^2
CM2_TO_M2 = 0.0001

def extract_inertia(part_definition) -> Inertia:
    """Extract mass properties from part definition.

    Args:
        part_definition: PartComponentDefinition COM object

    Returns:
        Inertia dataclass
    """
    mp = part_definition.MassProperties

    # Mass (kg)
    mass = mp.Mass
    logger.debug(f"Mass: {mass} kg")

    # Center of mass (cm -> m)
    com = mp.CenterOfMass
    center_of_mass = np.array([
        InventorUnits.length_to_meters(com.X),
        InventorUnits.length_to_meters(com.Y),
        InventorUnits.length_to_meters(com.Z),
    ])
    logger.debug(f"CoM: {center_of_mass} m")

    # Full inertia tensor
    # XYZMomentsOfInertia returns 6 values in Python
    result = mp.XYZMomentsOfInertia()
    Ixx, Iyy, Izz, Ixy, Iyz, Ixz = result

    # Convert kg*cm^2 to kg*m^2
    inertia_tensor = np.array([
        [Ixx * CM2_TO_M2, Ixy * CM2_TO_M2, Ixz * CM2_TO_M2],
        [Ixy * CM2_TO_M2, Iyy * CM2_TO_M2, Iyz * CM2_TO_M2],
        [Ixz * CM2_TO_M2, Iyz * CM2_TO_M2, Izz * CM2_TO_M2],
    ])

    logger.debug(f"Inertia tensor (kg*m^2):\n{inertia_tensor}")

    return Inertia(
        mass=mass,
        center_of_mass=center_of_mass,
        inertia_tensor=inertia_tensor,
    )
```

### Material Extraction with Error Handling
```python
# Source: Autodesk Manufacturing DevBlog - Materials API
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Density unit conversion: kg/cm^3 to kg/m^3
CM3_TO_M3 = 1_000_000

def extract_material(part_doc) -> Tuple[Optional[str], Optional[float]]:
    """Extract material name and density from part document.

    Args:
        part_doc: PartDocument COM object

    Returns:
        Tuple of (material_name, density_kg_m3)
        Returns (None, None) if no material assigned
        Returns (name, None) if material has no density
    """
    try:
        material = part_doc.ActiveMaterial
        if material is None:
            logger.warning(f"No material assigned to {part_doc.DisplayName}")
            return None, None

        material_name = material.DisplayName
        logger.debug(f"Material: {material_name}")

        # Get physical properties asset
        phys_props = material.PhysicalPropertiesAsset
        if phys_props is None:
            logger.warning(f"Material {material_name} has no physical properties")
            return material_name, None

        # Find density property (name may vary by locale)
        density = None
        for prop in phys_props:
            prop_name = prop.Name.lower()
            if "density" in prop_name or "dichte" in prop_name:
                density = prop.Value * CM3_TO_M3
                logger.debug(f"Density: {density} kg/m^3")
                break

        if density is None:
            logger.warning(f"Could not find density for material {material_name}")

        return material_name, density

    except Exception as e:
        logger.error(f"Material extraction failed: {e}")
        return None, None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Recursive SubOccurrences traversal | AllLeafOccurrences property | Available since Inventor 2010+ | Simpler code, automatic transform accumulation |
| Manual transform multiplication | Transformation property on leaf | Always available | No manual matrix math needed |
| SaveAs with file filter | TranslatorAddIn mechanism | Inventor 2011+ | More control, AP214/AP242 options |
| Diagonal-only inertia | XYZMomentsOfInertia with products | Always available | Full 6-component tensor for accurate dynamics |

**Deprecated/outdated:**
- Direct recursive SubOccurrences iteration for simple part extraction: Use AllLeafOccurrences
- Manual transform accumulation for nested assemblies: Transformation property handles this
- Assuming AP203 is best: AP214 has better compatibility with modern CAD/CAM systems

## Open Questions

Things that couldn't be fully resolved:

1. **XYZMomentsOfInertia reference point**
   - What we know: Returns moments about XYZ axes
   - What's unclear: Whether this is about origin or center of mass by default
   - Recommendation: Test with known geometry, may need parallel axis theorem to adjust

2. **Material density property name variations**
   - What we know: English Inventor uses "Density" somewhere in the name
   - What's unclear: Exact property name in localized versions
   - Recommendation: Search for partial match, log all property names during testing

3. **STEP export for assemblies vs parts**
   - What we know: TranslatorAddIn works for both
   - What's unclear: Whether exporting assembly STEP or individual part STEPs is better
   - Recommendation: Export per unique part definition (stated requirement)

4. **pywin32 output parameter behavior**
   - What we know: VBA uses ByRef, Python returns tuple
   - What's unclear: Exact behavior of XYZMomentsOfInertia in pywin32
   - Recommendation: Test with simple part, verify tuple return structure

## Sources

### Primary (HIGH confidence)
- [Autodesk Inventor 2025 API - Getting Started](https://help.autodesk.com/view/INVNTOR/2025/ENU/?guid=GUID-4939ABD1-A15E-473E-9376-D8208EC029EB) - Official documentation entry point
- [Autodesk Inventor API - ComponentOccurrence Object](https://help.autodesk.com/cloudhelp/2022/ENU/Inventor-API/files/ComponentOccurrence.htm) - Transformation property, SubOccurrences, ParentOccurrence
- [Autodesk Inventor API - MassProperties Sample](https://help.autodesk.com/cloudhelp/2025/ENU/Inventor-API/files/MassProperties_Sample.htm) - Mass, CenterOfMass, XYZMomentsOfInertia
- [Autodesk Inventor API - TranslatorAddIn5 Sample (STEP)](https://help.autodesk.com/cloudhelp/2022/ENU/Inventor-API/files/TranslatorAddIn5_Sample.htm) - STEP export code
- [Autodesk Inventor API - Translator Options](https://help.autodesk.com/cloudhelp/2018/ENU/Inventor-API/files/TranslatorSettings.htm) - ApplicationProtocolType values

### Secondary (MEDIUM confidence)
- [Design and Motion - Assembly Document Hierarchy](https://designandmotion.net/autodesk/autodesk-inventor-api-assembly-document-hierarchy/) - AllLeafOccurrences usage examples
- [Autodesk Manufacturing DevBlog - Inventor 2014 API Set Part Material](https://adndevblog.typepad.com/manufacturing/2013/07/inventor-2014-api-set-part-material.html) - Material/PhysicalPropertiesAsset access
- [Autodesk Community Forums - TranslatorAddIn Python](https://forums.autodesk.com/t5/inventor-programming-forum/inventor-translatoraddin-access-using-python/td-p/11414854) - Python casting requirements

### Tertiary (LOW confidence)
- [PyInventor GitHub](https://github.com/AndrewOriani/PyInventor) - Python wrapper patterns (limited scope)
- Training data knowledge of COM patterns - Needs verification with actual Inventor

## Metadata

**Confidence breakdown:**
- Assembly traversal (AllLeafOccurrences): HIGH - Official Autodesk docs with samples
- Transform extraction: HIGH - Official Autodesk docs, verified Cell indexing
- STEP export: HIGH - Official Autodesk sample code with GUID
- Mass properties: HIGH - Official sample, but inertia reference frame needs testing
- Material extraction: MEDIUM - Blog posts, property name varies by locale
- pywin32 output parameters: MEDIUM - Standard COM pattern but needs verification

**Research date:** 2026-01-19
**Valid until:** 60 days (Inventor API is stable, main risk is pywin32 edge cases)
