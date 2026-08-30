# Inventor Assembly Exporter & Importer

Export Autodesk Inventor assemblies to simulation formats (ADAMS, URDF, SDF, MuJoCo) and batch-import STL meshes into Inventor Part (.ipt) files.

## Requirements

- Windows (Inventor is Windows-only)
- Autodesk Inventor installed with COM access enabled
- Python 3.11+

## Installation

```bash
# Clone and install
git clone https://github.com/JonathanCamargo/InventorExport.git
cd InventorExport
pip install -e ".[dev]"
```

## Usage

1. Open an assembly in Autodesk Inventor
2. Run the exporter:

```bash
# Export to ADAMS View format
inventorexport --format adams --output model.cmd

# Export to URDF (ROS)
inventorexport --format urdf --output robot.urdf

# Export to MuJoCo
inventorexport --format mujoco --output model.xml

# Export to SDF (Gazebo)
inventorexport --format sdf --output model.sdf

# Export to glTF / GLB (Khronos, viewable in web viewers, Blender, three.js)
inventorexport --format glb --output model.glb    # binary (recommended)
inventorexport --format gltf --output model.gltf  # JSON + embedded buffer

# List available formats
inventorexport --list-formats
```

### Output Files

| Format | Main File | Geometry |
|--------|-----------|----------|
| ADAMS | `.cmd` | `.stp` (STEP) |
| URDF | `.urdf` | `.stl` (meshes/) |
| SDF | `.sdf` | `.stl` (meshes/) |
| MuJoCo | `.xml` | `.stl` (meshes/) |
| glTF/GLB | `.gltf` / `.glb` | Embedded in file (single-file output) |

### glTF/GLB export

The `glb`/`gltf` formats produce self-contained files viewable in Blender,
web viewers (three.js, `<model-viewer>`), Windows 3D Viewer, and most game
engines:

- **Geometry**: STEP files are meshed and embedded directly into the file —
  no external mesh folder needed. Binary STLs are also accepted as input.
- **Units**: vertices are converted from mm (pipeline meshes) to meters
  (glTF requirement) automatically.
- **Orientation**: a root node converts Inventor's Z-up to glTF's Y-up.
- **Hierarchy**: nodes follow the kinematic spanning tree (same structure as
  URDF/MuJoCo); rigid groups are merged into a single node.
- **Skeleton**: each part becomes a **bone** in a glTF skin (armature)
  following the kinematic tree, with meshes rigid-skinned to their bone —
  Blender, Unity, and Unreal import an animatable skeleton, and the joint
  structure defined in Inventor is preserved in the node graph. Closed-loop
  joints cannot live in the tree (glTF nodes are strictly hierarchical) and
  ride along in `extras` instead.
- **Materials**: PBR `pbrMetallicRoughness` with colors inferred from
  material names (steel, aluminum, plastic, rubber).
- **Joints**: glTF has no core joint concept, so constraint metadata
  (type, axis, origin, limits) is exported into the top-level `extras` field.
- **Reuse**: existing STL meshes in `meshes/` are reused without
  reconversion, so switching between URDF/MuJoCo and GLB exports of the same
  assembly is fast.
- **Mesh size**: glTF meshes use a coarser default tolerance (0.5 mm) than
  URDF/MuJoCo (0.1 mm) since GLB is typically used for visualization. File
  size scales with triangle count.

⚠️ **Stale mesh cache**: `MeshConverter` skips conversion when an STL with
the expected name already exists in `meshes/` — regardless of the tolerance
it was originally produced with. If you change tolerance settings (or
upgrade from an older version), **delete the `meshes/` folder before
re-exporting**, otherwise the old meshes are silently reused:

```powershell
Remove-Item -Recurse -Force path\to\output\meshes
inventorexport --format glb --output model.glb
```

To diagnose a large GLB, check which parts carry the most triangles:

```powershell
foreach ($f in Get-ChildItem path\to\output\meshes\*.stl) {
  $n = [BitConverter]::ToUInt32((Get-Content $f.FullName -Encoding Byte -TotalCount 84 -ReadCount 0), 80)
  "{0,10:N0} tris  {1,8:N1} KB  {2}" -f $n, ($f.Length/1KB), $f.Name
}
```

For further web-size reduction, post-process with
[gltfpack](https://github.com/zeux/meshoptimizer/tree/master/gltf)
(installs via npm):

```bash
gltfpack -i model.glb -o model_web.glb -cc -si 0.5
```

`-cc` applies meshopt compression (typically 5–10× smaller); `-si 0.5`
simplifies meshes another 50%. Meshopt-compressed files load directly in
three.js and `<model-viewer>`.

## STL Import

Batch-convert STL mesh files to Inventor Part (.ipt) files with solid bodies. The importer opens each STL in Inventor, converts the mesh to a BRep solid via the Mesh Enabler add-in, and saves the result as an IPT — fully automated, no manual clicks required.

```bash
# Convert all STL files in a folder (IPTs saved alongside originals)
inventorimport path/to/stl_folder

# Specify a separate output directory
inventorimport path/to/stl_folder --output path/to/ipt_output

# STL files are in inches (default assumes mm)
inventorimport path/to/stl_folder --units in

# Verbose logging
inventorimport path/to/stl_folder -v
```

**Note:** Requires the Mesh Enabler add-in to be installed in Inventor (included by default in Inventor 2025+).

### STL units and Inventor templates

STL files contain no unit information — vertex coordinates are just numbers. When Inventor opens an STL via `Documents.Open()`, it interprets those numbers using the **default part template's length units**. If your template uses inches (common in US installations) but the STL was designed in millimeters, every dimension will be 25.4x too large.

`inventorimport` handles this automatically: it detects your Inventor template's units, compares them to the `--units` flag (default: `mm`), and prescales the STL vertices before opening so that Inventor's interpretation produces the correct geometry regardless of template settings.

| STL units | Template units | What happens |
|-----------|---------------|--------------|
| mm | mm | No correction needed |
| mm | in | Vertices prescaled by 1/25.4 |
| in | mm | Vertices prescaled by 25.4 |
| any | any | Automatic compensation |

## Units

Understanding unit handling is important for getting correctly-scaled output.

### Export pipeline (inventorexport)

```
Inventor internal (cm) → STEP file → OCCT/CadQuery (mm) → STL meshes (mm)
```

- **Inventor** always stores geometry in centimeters internally, regardless of document display settings.
- **STEP export** writes geometry with a unit header. OCCT (the geometry kernel inside CadQuery) reads this header and normalizes all coordinates to **millimeters**.
- **STL meshes** produced by the export pipeline are always in **mm**.
- **Body positions, rotations, mass, and inertia** are extracted from Inventor and converted to SI units (meters, kg, kg·m²) in the internal representation.

The format writers account for the mm mesh / meters body mismatch:

| Format | Body units | Mesh units | Mesh scale applied |
|--------|-----------|------------|-------------------|
| MuJoCo | meters | mm | `scale="0.001 0.001 0.001"` on `<mesh>` |
| URDF | meters | mm | `scale="0.001 0.001 0.001"` on `<mesh>` |
| SDF | meters | mm | `<scale>0.001 0.001 0.001</scale>` |
| glTF/GLB | meters | mm | Vertex data scaled by 0.001 when embedding |
| ADAMS | mm | N/A (uses STEP) | No conversion needed |

### Debugging transform issues

If body positions appear wrong (e.g., all zeros), use `--debug-transforms` to dump the raw 4x4 transformation matrix for each part:

```bash
inventorexport --format mujoco --output model.xml --debug-transforms
```

This logs the full matrix without enabling all verbose output, helping diagnose whether Inventor is returning identity transforms for certain assembly types.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=inventor_exporter

# Run specific test module
pytest tests/core/test_units.py
pytest tests/writers/test_urdf.py
```

### Test Structure

```
tests/
  core/           # Unit conversion, rotation math, COM utilities
  model/          # Data model (Transform, Body, AssemblyModel)
  writers/        # Format writers (ADAMS, URDF, SDF, MuJoCo, glTF/GLB)
  extraction/     # Inventor data extraction (mocked)
  cli/            # CLI integration tests
```

Note: Extraction tests use mocks since they require a running Inventor instance.

## Project Structure

```
src/inventor_exporter/
  core/           # Utilities (units, rotation, COM, logging)
  model/          # Data model (AssemblyModel, Body, Material, Transform)
  extraction/     # Inventor COM automation (traversal, STEP export)
  writers/        # Format writers (FormatWriter protocol + implementations)
  importing/      # STL-to-IPT batch import (mesh conversion via COM)
  cli.py          # Click-based CLI (inventorexport + inventorimport)
```

## Adding a New Format

1. Create `src/inventor_exporter/writers/myformat.py`
2. Implement the `FormatWriter` protocol:

```python
from inventor_exporter.writers.registry import WriterRegistry

@WriterRegistry.register("myformat")
class MyFormatWriter:
    def write(self, model: AssemblyModel, output_path: Path) -> None:
        # Generate output file
        pass
```

3. The format is automatically available via `--format myformat`

## License

MIT

This repository was developed with the assistance of Claude code-generation tools. Portions of the code, documentation, and structural scaffolding may have been produced or refined using AI-assisted generation.
Users of this repository should evaluate the software according to their own quality, security, and compliance standards before deploying it in production environments.
