# Phase 6: Additional Writers - Research

**Researched:** 2026-01-20
**Domain:** Robot description formats (URDF, SDF, MJCF) and mesh conversion
**Confidence:** HIGH

## Summary

Phase 6 implements three robot description format writers: URDF (ROS-compatible), SDF (Gazebo), and MuJoCo MJCF. All three are XML-based formats with different conventions for describing robot kinematics and geometry. The existing infrastructure (FormatWriter protocol, WriterRegistry, rotation utilities) provides a solid foundation.

Key findings:
- **URDF** uses `<link>` and `<joint>` elements with RPY angles (roll-pitch-yaw, radians), meters for positions
- **SDF** extends URDF capabilities with `<model>`, `<link>`, `<joint>`, `<pose>` elements; supports both RPY and quaternions
- **MuJoCo MJCF** uses `<worldbody>`, `<body>`, `<geom>` with quaternions (w,x,y,z) and meters; assets defined separately

**Primary recommendation:** Use lxml for XML generation (already a dependency pattern in ecosystem), implement each writer following the AdamsWriter pattern, and use CadQuery or PythonOCC for STEP-to-STL conversion.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lxml | >=4.9 | XML generation and schema validation | Industry standard for Python XML; supports XSD validation |
| CadQuery | >=2.2 | STEP to STL mesh conversion | Pure pip install, based on OCCT, cleaner API than PythonOCC |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pythonocc-core | >=7.9 | Alternative STEP to STL | Only if CadQuery unavailable; requires conda |
| numpy-stl | >=3.0 | STL file manipulation | Post-processing if needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CadQuery | pythonocc-core | pythonocc requires conda, not pip-installable |
| lxml | xml.etree.ElementTree | stdlib but lacks XSD validation support |
| CadQuery | FreeCAD Python | Heavyweight dependency, harder installation |

**Installation:**
```bash
pip install lxml cadquery
```

Note: CadQuery installation may require specific Python versions (3.9-3.12). On Windows, if CadQuery fails, fall back to PythonOCC via conda.

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/writers/
    __init__.py
    protocol.py          # Existing FormatWriter Protocol
    registry.py          # Existing WriterRegistry
    adams.py             # Existing AdamsWriter (reference)
    urdf.py              # NEW: URDFWriter
    sdf.py               # NEW: SDFWriter
    mujoco.py            # NEW: MuJoCoWriter
    mesh_converter.py    # NEW: STEP to STL conversion utilities
```

### Pattern 1: XML Builder Pattern with lxml
**What:** Use lxml.etree.SubElement for structured XML construction
**When to use:** All XML format writers
**Example:**
```python
# Source: lxml documentation
from lxml import etree

def build_robot_xml(model: AssemblyModel) -> etree._Element:
    robot = etree.Element("robot", name=model.name)

    # Add base_link (virtual frame at world origin)
    base_link = etree.SubElement(robot, "link", name="base_link")

    for body in model.bodies:
        # Add link element
        link = etree.SubElement(robot, "link", name=body.name)
        # Add visual, collision, inertial children...

        # Add fixed joint connecting to base_link
        joint = etree.SubElement(robot, "joint",
                                 name=f"{body.name}_joint",
                                 type="fixed")
        parent = etree.SubElement(joint, "parent", link="base_link")
        child = etree.SubElement(joint, "child", link=body.name)

    return robot
```

### Pattern 2: Coordinate Convention Conversion
**What:** Convert IR (meters, rotation matrix) to format-specific conventions
**When to use:** Every writer
**Example:**
```python
# URDF: meters, RPY radians
from inventor_exporter.core.rotation import rotation_to_euler, EulerConvention

def format_urdf_origin(transform: Transform) -> dict:
    """Convert transform to URDF origin attributes."""
    rpy = rotation_to_euler(transform.rotation, EulerConvention.URDF_RPY, degrees=False)
    return {
        "xyz": f"{transform.position[0]} {transform.position[1]} {transform.position[2]}",
        "rpy": f"{rpy[0]} {rpy[1]} {rpy[2]}"
    }

# MuJoCo: meters, quaternion (w,x,y,z)
from inventor_exporter.core.rotation import rotation_to_quaternion

def format_mujoco_body(transform: Transform) -> dict:
    """Convert transform to MuJoCo body attributes."""
    quat = rotation_to_quaternion(transform.rotation, scalar_first=True)
    return {
        "pos": f"{transform.position[0]} {transform.position[1]} {transform.position[2]}",
        "quat": f"{quat[0]} {quat[1]} {quat[2]} {quat[3]}"
    }
```

### Pattern 3: Asset/Material Separation
**What:** Define materials/meshes once, reference by name
**When to use:** All formats (matches user decision in CONTEXT.md)
**Example:**
```xml
<!-- URDF: materials defined at robot level -->
<robot name="assembly">
  <material name="steel">
    <color rgba="0.7 0.7 0.7 1.0"/>
  </material>
  <link name="part1">
    <visual>
      <material name="steel"/>  <!-- reference -->
    </visual>
  </link>
</robot>

<!-- MuJoCo: assets in separate section -->
<mujoco>
  <asset>
    <mesh name="part1_mesh" file="meshes/part1.stl"/>
    <material name="steel" rgba="0.7 0.7 0.7 1"/>
  </asset>
  <worldbody>
    <body name="part1">
      <geom type="mesh" mesh="part1_mesh" material="steel"/>
    </body>
  </worldbody>
</mujoco>
```

### Pattern 4: Base Link Convention
**What:** Create virtual base_link at world origin, connect bodies via fixed joints
**When to use:** URDF and SDF (standard robot convention)
**Example:**
```xml
<!-- URDF base_link pattern -->
<robot name="assembly">
  <!-- Virtual base at world origin (no geometry) -->
  <link name="base_link"/>

  <!-- Physical body -->
  <link name="part1">
    <visual>...</visual>
    <collision>...</collision>
    <inertial>...</inertial>
  </link>

  <!-- Fixed joint attaches part1 to base_link -->
  <joint name="part1_joint" type="fixed">
    <parent link="base_link"/>
    <child link="part1"/>
    <origin xyz="1.0 2.0 3.0" rpy="0 0 0"/>
  </joint>
</robot>
```

### Anti-Patterns to Avoid
- **Inline material definitions:** Define materials once at top level, not inline per visual
- **Hardcoded units:** Always convert from IR (meters) to format units explicitly
- **Missing collision geometry:** Per CONTEXT.md, collision = visual; always include both
- **Nested body hierarchy in URDF:** URDF is tree-based; use flat structure with fixed joints

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| STEP to STL conversion | Custom mesh tessellation | CadQuery exporters | OCCT-based, handles complex geometry, configurable quality |
| Quaternion math | Manual rotation conversion | scipy.spatial.transform.Rotation | Handles gimbal lock, edge cases |
| XML generation | String concatenation | lxml.etree | Proper escaping, namespace handling, pretty printing |
| XSD validation | Custom element checking | lxml.etree.XMLSchema | Standard compliance, detailed error messages |
| RPY angle extraction | Manual matrix decomposition | rotation_to_euler() | Already exists in core.rotation module |

**Key insight:** The rotation utilities already exist in `inventor_exporter.core.rotation` with `rotation_to_euler()` for URDF RPY and `rotation_to_quaternion()` for MuJoCo. Do not reimplement.

## Common Pitfalls

### Pitfall 1: URDF Coordinate Frame Confusion
**What goes wrong:** Mixing up which frame the origin is relative to
**Why it happens:** URDF joint origin is relative to parent link, not world
**How to avoid:** For fixed joints from base_link, the joint origin IS the body's world position
**Warning signs:** Bodies appearing at wrong locations in visualizer

### Pitfall 2: MuJoCo Mesh Centering
**What goes wrong:** Meshes appear offset from body position
**Why it happens:** MuJoCo centers meshes at geometric center by default
**How to avoid:** Set `<compiler meshdir="meshes"/>` and use consistent mesh origins; or use refpos/refquat to adjust
**Warning signs:** Visual geometry not aligned with collision geometry

### Pitfall 3: Quaternion Convention Mismatch
**What goes wrong:** Rotations appear wrong (90-degree errors, flipped axes)
**Why it happens:** Different libraries use (w,x,y,z) vs (x,y,z,w) ordering
**How to avoid:** MuJoCo uses (w,x,y,z) - use `rotation_to_quaternion(matrix, scalar_first=True)`
**Warning signs:** Parts rotated 180 degrees or oriented completely wrong

### Pitfall 4: STL Binary vs ASCII
**What goes wrong:** Large file sizes, slow loading
**Why it happens:** ASCII STL files are much larger than binary
**How to avoid:** Always export binary STL: `cq.exporters.export(shape, "file.stl", ascii=False)` or CadQuery default
**Warning signs:** Mesh files are 5-10x larger than expected

### Pitfall 5: Missing Inertial Elements
**What goes wrong:** Simulation physics behave incorrectly or links are ignored
**Why it happens:** Links without inertia may be treated as massless or skipped
**How to avoid:** Always include `<inertial>` with mass and inertia tensor for each link
**Warning signs:** URDF to SDF conversion warnings, links not appearing in simulation

### Pitfall 6: Mesh File Path Resolution
**What goes wrong:** Simulator cannot find mesh files
**Why it happens:** Absolute paths don't work cross-platform; relative paths computed wrong
**How to avoid:** Use relative paths from XML file location; place meshes in `meshes/` subdirectory
**Warning signs:** "File not found" errors when loading model

## Code Examples

Verified patterns from official sources:

### URDF Link Element
```xml
<!-- Source: https://wiki.ros.org/urdf/XML/link -->
<link name="part1">
  <inertial>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <mass value="1.0"/>
    <inertia ixx="0.1" ixy="0" ixz="0" iyy="0.1" iyz="0" izz="0.1"/>
  </inertial>
  <visual>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <geometry>
      <mesh filename="meshes/part1.stl"/>
    </geometry>
    <material name="steel"/>
  </visual>
  <collision>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <geometry>
      <mesh filename="meshes/part1.stl"/>
    </geometry>
  </collision>
</link>
```

### URDF Fixed Joint
```xml
<!-- Source: https://wiki.ros.org/urdf/XML/joint -->
<joint name="part1_joint" type="fixed">
  <parent link="base_link"/>
  <child link="part1"/>
  <origin xyz="1.0 2.0 3.0" rpy="0.1 0.2 0.3"/>
</joint>
```

### SDF Model Structure
```xml
<!-- Source: http://sdformat.org/spec -->
<sdf version="1.8">
  <model name="assembly">
    <link name="base_link"/>
    <link name="part1">
      <pose relative_to="base_link">1.0 2.0 3.0 0.1 0.2 0.3</pose>
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>0.1</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>0.1</iyy><iyz>0</iyz><izz>0.1</izz>
        </inertia>
      </inertial>
      <visual name="visual">
        <geometry>
          <mesh><uri>meshes/part1.stl</uri></mesh>
        </geometry>
      </visual>
      <collision name="collision">
        <geometry>
          <mesh><uri>meshes/part1.stl</uri></mesh>
        </geometry>
      </collision>
    </link>
    <joint name="part1_joint" type="fixed">
      <parent>base_link</parent>
      <child>part1</child>
    </joint>
  </model>
</sdf>
```

### MuJoCo MJCF Structure
```xml
<!-- Source: https://mujoco.readthedocs.io/en/stable/XMLreference.html -->
<mujoco model="assembly">
  <compiler meshdir="meshes"/>

  <asset>
    <mesh name="part1_mesh" file="part1.stl"/>
    <material name="steel" rgba="0.7 0.7 0.7 1"/>
  </asset>

  <worldbody>
    <!-- base_link is implicit (world frame) in MuJoCo -->
    <body name="part1" pos="1.0 2.0 3.0" quat="1 0 0 0">
      <inertial pos="0 0 0" mass="1.0"
                diaginertia="0.1 0.1 0.1"/>
      <geom type="mesh" mesh="part1_mesh" material="steel"/>
    </body>
  </worldbody>
</mujoco>
```

### CadQuery STEP to STL Conversion
```python
# Source: https://cadquery.readthedocs.io/en/latest/importexport.html
import cadquery as cq
from pathlib import Path

def convert_step_to_stl(
    step_path: Path,
    stl_path: Path,
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1
) -> None:
    """Convert STEP file to binary STL.

    Args:
        step_path: Input STEP file path
        stl_path: Output STL file path
        tolerance: Linear deflection (mm). Lower = finer mesh.
        angular_tolerance: Angular deflection (radians). Lower = smoother curves.
    """
    shape = cq.importers.importStep(str(step_path))
    cq.exporters.export(
        shape,
        str(stl_path),
        exportType="STL",
        tolerance=tolerance,
        angularTolerance=angular_tolerance,
    )
```

### lxml Schema Validation
```python
# Source: https://lxml.de/validation.html
from lxml import etree
from pathlib import Path

def validate_urdf(xml_content: str, schema_path: Path) -> list[str]:
    """Validate URDF XML against XSD schema.

    Args:
        xml_content: URDF XML string
        schema_path: Path to urdf.xsd schema file

    Returns:
        List of validation error messages (empty if valid)
    """
    schema_doc = etree.parse(str(schema_path))
    schema = etree.XMLSchema(schema_doc)

    doc = etree.fromstring(xml_content.encode())

    if schema.validate(doc):
        return []

    return [str(error) for error in schema.error_log]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| URDF only for ROS | URDF + SDF for Gazebo | 2015+ | SDF preferred for Gazebo, URDF still standard for ROS tools |
| MuJoCo proprietary | MuJoCo open source (DeepMind) | 2022 | Wider adoption, better documentation |
| MuJoCo 2.x | MuJoCo 3.x | 2024 | New features (flex, attach), mostly backward compatible |
| Gazebo Classic | Gazebo (ignition-based) | Jan 2025 EOL | SDF format continues, simulation engine changed |

**Deprecated/outdated:**
- Gazebo Classic: Reached end-of-life January 2025; new Gazebo uses same SDF format
- MuJoCo 2.x: Still works but 3.x recommended for new projects
- URDF xacro macros: Not needed for generated files; use for hand-authored URDF only

## Format Comparison Reference

| Aspect | URDF | SDF | MuJoCo MJCF |
|--------|------|-----|-------------|
| File extension | .urdf | .sdf | .xml |
| Root element | `<robot>` | `<sdf><model>` | `<mujoco>` |
| Position units | meters | meters | meters |
| Rotation format | RPY (radians) | RPY (radians) or quat | quat (w,x,y,z) |
| Mesh formats | STL, DAE, OBJ | STL, DAE, OBJ | STL, OBJ, MSH |
| Mesh reference | `filename="..."` | `<uri>...</uri>` | `mesh="name"` (via asset) |
| Kinematics | tree only | tree or graph | tree (nested bodies) |
| Base frame | explicit base_link | explicit or model frame | worldbody (implicit) |
| Schema available | Yes (urdf.xsd) | Yes (sdf.xsd) | Community XSD available |

## Open Questions

Things that couldn't be fully resolved:

1. **CadQuery Windows Installation Reliability**
   - What we know: CadQuery is pip-installable but may have issues on some Windows/Python combinations
   - What's unclear: Exact compatibility matrix with Python 3.11/3.12/3.13 on Windows
   - Recommendation: Try CadQuery first; fall back to subprocess call to FreeCAD or skip mesh conversion with warning

2. **SDF Schema Validation**
   - What we know: SDFormat has schema files in the gazebosim/sdformat repo
   - What's unclear: Whether lxml can validate against all SDF versions
   - Recommendation: Validate against SDF 1.8; document schema location

3. **MuJoCo Schema Official Status**
   - What we know: Community XSD exists at ronansgd/xml-schema-mjcf; MuJoCo has internal schema via `mj_printSchema`
   - What's unclear: Whether community schema is complete for MuJoCo 3.x
   - Recommendation: Use community schema for basic validation; test with actual MuJoCo loading

## Sources

### Primary (HIGH confidence)
- [ROS URDF Link Specification](https://wiki.ros.org/urdf/XML/link) - Link element structure, inertial format
- [ROS URDF Joint Specification](https://wiki.ros.org/urdf/XML/joint) - Joint types, origin format
- [MuJoCo XML Reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html) - Complete MJCF specification
- [SDFormat Specification](http://sdformat.org/spec) - SDF element structure
- [lxml Validation](https://lxml.de/validation.html) - XMLSchema validation API
- [CadQuery Import/Export](https://cadquery.readthedocs.io/en/latest/importexport.html) - STEP and STL handling

### Secondary (MEDIUM confidence)
- [URDF XSD Schema](https://github.com/ros/urdfdom/blob/master/xsd/urdf.xsd) - Official URDF schema
- [MuJoCo Community XSD](https://github.com/ronansgd/xml-schema-mjcf) - Community MJCF schema
- [PythonOCC DataExchange](https://github.com/tpaviot/pythonocc-core/blob/master/src/Extend/DataExchange.py) - STEP/STL conversion functions

### Tertiary (LOW confidence)
- Various tutorial sites for format usage examples
- Community discussions on mesh coordinate systems

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - lxml and CadQuery well-documented, existing examples
- Architecture: HIGH - follows established AdamsWriter pattern
- Format specifications: HIGH - official documentation consulted
- Pitfalls: MEDIUM - based on documentation and known issues
- Schema validation: MEDIUM - schemas exist but coverage unclear

**Research date:** 2026-01-20
**Valid until:** 60 days (formats are stable; MuJoCo minor versions may add features)
