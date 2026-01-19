# Feature Landscape

**Domain:** CAD-to-Multibody Dynamics Simulation Export
**Researched:** 2026-01-19
**Overall Confidence:** MEDIUM (based on training data for format specifications, HIGH for VBA baseline analysis)

## Executive Summary

CAD-to-simulation exporters bridge mechanical design (CAD assemblies) with physics simulation (multibody dynamics). The core challenge is extracting kinematic structure, inertial properties, and geometric representations from CAD and translating them to simulation-specific formats.

The existing VBA implementation handles a subset of what simulation formats support: rigid body definitions, transformations (position + Euler angles), geometry references, and material-based mass properties. Key gaps include joint/constraint extraction, inertia tensor calculation, and collision geometry generation.

## Table Stakes

Features users expect from any CAD-to-simulation exporter. Missing any of these makes the tool feel incomplete.

| Feature | Why Expected | Complexity | Current VBA | Notes |
|---------|--------------|------------|-------------|-------|
| **Assembly traversal** | Core function - must walk assembly tree | Medium | YES | VBA uses `AllLeafOccurrences` |
| **Part geometry export** | Simulations need visual/collision geometry | Low | YES (STEP) | VBA exports AP214 STEP |
| **Transformation extraction** | Part positions in assembly coordinate frame | Medium | YES | Translation vector + Euler angles |
| **Rigid body definitions** | Every simulation format has bodies/links | Low | YES | Generated per occurrence |
| **Material property extraction** | Mass/density needed for dynamics | Medium | PARTIAL | VBA retrieves but hardcodes values |
| **Mass properties** | Simulations need mass, sometimes inertia | High | PARTIAL | Only material-based, no inertia tensor |
| **Unique naming** | Parts need unique identifiers | Low | YES | Replaces `:` with `_` |
| **Coordinate frame handling** | CAD and sim may use different conventions | Medium | YES | Ground reference frame logic |
| **Output file generation** | Must produce valid format-specific files | Medium | YES | ADAMS .cmd files |
| **Multi-instance support** | Same part used multiple times needs handling | Medium | YES | Leaf occurrences are instances |

### Table Stakes Detail

**Assembly Traversal**
- Must handle nested subassemblies (current VBA uses leaf occurrences which flattens hierarchy)
- Must track parent-child relationships for hierarchical formats (URDF)
- URDF requires tree structure; ADAMS/MuJoCo are more flexible

**Geometry Export**
- STEP is universal neutral format (current approach is correct)
- Some formats prefer STL for collision geometry
- Visual vs collision geometry distinction matters for MuJoCo

**Mass Properties Calculation**
- From material: density + volume = mass
- Inertia tensor: critical for accurate dynamics
- Center of mass: required by all target formats
- Current VBA only assigns material; actual inertia calculation is missing

## Differentiators

Features that set a tool apart. Not expected by default, but provide significant value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Joint/constraint extraction** | Automatic kinematic chain generation | HIGH | VBA lacks this entirely |
| **Inertia tensor calculation** | Accurate rotational dynamics | MEDIUM | Inventor API provides this |
| **Collision geometry generation** | Convex hull or simplified shapes | HIGH | Needed for contact simulation |
| **Multi-format export** | One extraction, multiple outputs | MEDIUM | Core project goal |
| **Assembly hierarchy preservation** | URDF needs tree, not flat list | MEDIUM | Critical for robot models |
| **Marker/frame extraction** | Named reference frames from CAD | MEDIUM | Useful for sensors, tool frames |
| **Automatic joint type detection** | Revolute vs prismatic vs fixed | HIGH | Requires constraint analysis |
| **Joint limits extraction** | Range of motion from constraints | HIGH | Requires constraint analysis |
| **Validation/preview** | Check output before simulation | MEDIUM | Useful for debugging |
| **Incremental export** | Only re-export changed parts | MEDIUM | Performance for large assemblies |

### Differentiator Detail

**Joint/Constraint Extraction**

This is the highest-value differentiator. Currently:
- VBA exports only rigid bodies with no kinematic relationships
- Simulation users must manually add joints in the target software
- Inventor assembly constraints (mate, flush, angle, insert) encode joint semantics

Value: Extracting joints automatically converts a "geometry dump" into a "working model."

Complexity: HIGH because:
- Inventor constraints don't map 1:1 to simulation joints
- Multiple constraints together define one kinematic joint
- Requires heuristics or user hints to resolve ambiguity

**Inertia Tensor Calculation**

Required for accurate rotational dynamics. Inventor's COM API provides:
- `MassProperties.PrincipalMomentsOfInertia`
- `MassProperties.PrincipalAxesOfInertia`
- `MassProperties.CenterOfMass`

Current VBA references material but doesn't extract actual inertia values.

**Assembly Hierarchy Preservation**

URDF requires a strict tree structure:
- Root link (typically "world" or "base")
- Each link has exactly one parent
- Joints connect parent-to-child

ADAMS View and MuJoCo are more flexible but still benefit from hierarchical organization.

Current VBA flattens hierarchy - all parts are direct children of ground.

## Format-Specific Features

Each target format has unique requirements and capabilities.

### ADAMS View (.cmd)

| Feature | Status | Notes |
|---------|--------|-------|
| Rigid body creation | IMPLEMENTED | `part create rigid_body name_and_position` |
| Material assignment | IMPLEMENTED | `material create` + assignment |
| Geometry import | IMPLEMENTED | `file geometry read` for STEP |
| Markers | NOT IMPLEMENTED | Reference frames, needed for joints |
| Joints | NOT IMPLEMENTED | `constraint create joint` commands |
| Forces/contacts | NOT IMPLEMENTED | Applied elements |
| Simscript execution | NOT IMPLEMENTED | Post-processing |

### URDF (Robot Description Format)

| Feature | Required | Notes |
|---------|----------|-------|
| Links with inertial | YES | `<link><inertial>` with mass, inertia tensor, CoM |
| Visual geometry | YES | `<visual><geometry>` mesh reference |
| Collision geometry | YES | `<collision><geometry>` often simplified |
| Joints | YES | `<joint type="revolute|prismatic|fixed">` |
| Joint limits | YES | `<limit lower="" upper="" effort="" velocity="">` |
| Parent-child hierarchy | YES | Strict tree structure, no loops |
| Material colors | OPTIONAL | `<material><color rgba="">` |
| Transmissions | OPTIONAL | Actuator specifications |
| Gazebo extensions | OPTIONAL | `<gazebo>` tags for simulation-specific params |

### MuJoCo MJCF

| Feature | Required | Notes |
|---------|----------|-------|
| Bodies with inertial | YES | `<body><inertial>` |
| Geoms | YES | Multiple geoms per body for visual+collision |
| Joints | YES | `<joint type="">` within body |
| Meshes | YES | `<mesh file="">` with STL or OBJ preferred |
| Materials | OPTIONAL | `<material>` for appearance |
| Actuators | OPTIONAL | `<actuator>` for control |
| Contact pairs | OPTIONAL | `<contact>` for collision filtering |
| Compiler settings | IMPORTANT | `<compiler>` for coordinate conventions |

### Feature Coverage Matrix

| Feature | ADAMS | URDF | MuJoCo | Current VBA |
|---------|-------|------|--------|-------------|
| Rigid bodies/links | YES | YES | YES | YES |
| Position | YES | YES | YES | YES |
| Orientation | YES | YES | YES | YES |
| Mass | YES | YES | YES | PARTIAL |
| Inertia tensor | YES | YES | YES | NO |
| Center of mass | YES | YES | YES | NO |
| Visual geometry | YES | YES | YES | YES |
| Collision geometry | Optional | YES | YES | NO |
| Joints | YES | YES | YES | NO |
| Joint limits | YES | YES | YES | NO |
| Hierarchy | Flat OK | Tree required | Tree preferred | Flat |

## Anti-Features

Features to deliberately NOT build in v1. Common over-engineering mistakes in this domain.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **GUI interface** | Scope creep; CLI sufficient for automation | CLI with clear arguments |
| **Bi-directional sync** | Massive complexity, rarely works well | One-way export only |
| **Full constraint solver** | Reinventing physics engines | Export to simulation, let it solve |
| **Real-time preview** | Requires 3D rendering infrastructure | Export and view in target tool |
| **Assembly editing** | CAD tools do this better | Read-only from Inventor |
| **Multiple CAD sources** | Each CAD API is different | Inventor-only in v1 |
| **Automatic simplification** | Complex geometry algorithms | Export full geometry, simplify externally |
| **Joint synthesis** | Determining joint types from geometry alone | Require user hints or metadata |
| **Contact auto-generation** | Combinatorial explosion | Let simulation tool handle |
| **Format auto-detection** | Ambiguous and error-prone | Explicit format selection |

### Why These Are Anti-Features

**GUI Interface**
The project goal is automation and extensibility. A GUI:
- Adds significant development cost
- Reduces scriptability
- Diverts effort from core export logic

**Bi-directional Sync**
The temptation to "round-trip" models (CAD <-> Sim <-> CAD) is strong but:
- Simulation models diverge from CAD (tuned parameters, simplified geometry)
- Merge conflicts are unresolvable
- Each direction is a full project

**Joint Synthesis Without Hints**
Automatically determining joint types from CAD constraints is:
- Ambiguous (multiple valid interpretations)
- Fragile (depends on modeling style)
- Better handled with explicit metadata or user input

## Feature Dependencies

Understanding what depends on what for implementation ordering.

```
Assembly Traversal (foundation)
    |
    +-- Transformation Extraction
    |       |
    |       +-- Position/Orientation for bodies
    |
    +-- Part Geometry Export (STEP)
    |       |
    |       +-- Visual geometry references
    |       +-- Collision geometry (if simplified)
    |
    +-- Material Extraction
            |
            +-- Mass Properties
                    |
                    +-- Inertia Tensor Calculation
                    +-- Center of Mass

Joint Extraction (independent track)
    |
    +-- Constraint Analysis
    |       |
    |       +-- Joint Type Detection
    |       +-- Joint Axis Determination
    |
    +-- Joint Limits Extraction

Format Writers (depend on data model)
    |
    +-- ADAMS Writer (existing parity)
    +-- URDF Writer (requires hierarchy + joints for usefulness)
    +-- MuJoCo Writer (requires joints for usefulness)
```

### Dependency Implications

1. **Core data extraction** must come first (assembly, transforms, geometry, materials)
2. **Mass/inertia** builds on material extraction
3. **Joint extraction** is independent track but needed for URDF/MuJoCo value
4. **Format writers** are parallel once data model exists

## MVP Recommendation

For MVP (parity with VBA + architecture), prioritize:

### Must Have
1. **Assembly traversal** with hierarchy preservation (not just flat leaves)
2. **Transformation extraction** (position + orientation matrix)
3. **STEP geometry export** (existing capability)
4. **Material extraction** with actual property lookup (fix VBA bug)
5. **Mass properties** including inertia tensor from Inventor API
6. **ADAMS format writer** (feature parity with VBA)
7. **Format writer plugin interface** (core architectural goal)

### Should Have
8. **Center of mass extraction** (Inventor provides this)
9. **Unique naming with collision handling** (improve over VBA's simple replace)
10. **Validation** of output structure before writing

### Defer to v2
- **Joint/constraint extraction** - HIGH complexity, research spike needed
- **URDF writer** - Less valuable without joints
- **MuJoCo writer** - Less valuable without joints
- **Collision geometry generation** - Complex geometry algorithms
- **Incremental export** - Optimization, not critical path

### Rationale

The existing VBA creates "geometry dumps" - rigid bodies positioned correctly but with no kinematic relationships. While this is useful (users can add joints manually), the real value unlock is joint extraction.

However, joint extraction is HIGH complexity and poorly defined. MVP should:
1. Achieve VBA parity (proof of architecture)
2. Fix VBA bugs (material properties, inertia)
3. Establish plugin pattern for formats
4. Leave joint extraction for focused v2 effort

## Data Extraction Requirements

What the Python implementation must extract from Inventor for each format.

### Required from Inventor API

| Data | API Source | Used By |
|------|-----------|---------|
| Assembly structure | `AssemblyDocument.ComponentDefinition.Occurrences` | All |
| Part documents | `ComponentOccurrence.Definition.Document` | All |
| Transformation matrix | `ComponentOccurrence.Transformation` | All |
| Material name | `PartDocument.ActiveMaterial.DisplayName` | All |
| Material density | Material asset properties | All |
| Mass | `PartComponentDefinition.MassProperties.Mass` | All |
| Center of mass | `PartComponentDefinition.MassProperties.CenterOfMass` | All |
| Moments of inertia | `PartComponentDefinition.MassProperties.PrincipalMomentsOfInertia` | All |
| Principal axes | `PartComponentDefinition.MassProperties.PrincipalAxesOfInertia` | All |
| Bounding box | `PartDocument.ComponentDefinition.RangeBox` | URDF/MuJoCo |
| Assembly constraints | `AssemblyComponentDefinition.Constraints` | Joints (v2) |

### Data Model Shape

The intermediate representation should capture:

```
Assembly
  +-- name: str
  +-- parts: List[Part]
  +-- occurrences: List[Occurrence]
  +-- constraints: List[Constraint]  # v2

Part
  +-- name: str
  +-- geometry_file: Path  # STEP export
  +-- material: Material

Occurrence
  +-- name: str  # unique instance name
  +-- part: Part  # reference to part definition
  +-- transform: Transform
  +-- mass_properties: MassProperties
  +-- parent: Optional[Occurrence]  # for hierarchy

Transform
  +-- translation: Vector3
  +-- rotation: Matrix3x3 or Quaternion
  +-- euler_angles: EulerAngles  # for formats that need it

MassProperties
  +-- mass: float
  +-- center_of_mass: Vector3
  +-- inertia_tensor: Matrix3x3  # in body frame

Material
  +-- name: str
  +-- density: float
  +-- youngs_modulus: Optional[float]
  +-- poissons_ratio: Optional[float]
```

## Confidence Notes

| Finding | Confidence | Basis |
|---------|------------|-------|
| VBA capabilities | HIGH | Direct code analysis |
| ADAMS .cmd format | HIGH | VBA output analysis |
| URDF requirements | MEDIUM | Training data (ROS wiki, URDF spec) |
| MuJoCo MJCF requirements | MEDIUM | Training data (MuJoCo docs) |
| Inventor API capabilities | MEDIUM | Training data (Inventor SDK docs) |
| Joint extraction complexity | HIGH | Domain experience + VBA gap analysis |

**Note:** WebSearch was unavailable for verification. URDF and MuJoCo format details are based on training data which may be 6-18 months stale. Recommend verifying current format specs during implementation phase.

## Sources

- Direct analysis: `D:/git/inventorexport/Main.bas`, `Export.bas`, `Misc.bas`
- Project context: `.planning/PROJECT.md`, `.planning/codebase/*.md`
- Format specifications: Training data (URDF/ROS wiki, MuJoCo documentation, ADAMS View help)
- Inventor API: Training data (Autodesk Inventor API documentation)

---

*Feature research: 2026-01-19*
