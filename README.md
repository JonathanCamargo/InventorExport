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

# Verbose logging
inventorimport path/to/stl_folder -v
```

**Note:** Requires the Mesh Enabler add-in to be installed in Inventor (included by default in Inventor 2025+).

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
