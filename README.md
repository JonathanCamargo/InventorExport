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
  writers/        # Format writers (ADAMS, URDF, SDF, MuJoCo)
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
