"""STEP to STL mesh conversion utilities.

Provides mesh conversion for robot description formats (URDF, SDF, MuJoCo)
that require STL mesh files instead of STEP geometry.

Uses CadQuery for STEP import and STL export. If CadQuery is not available,
provides clear error message with installation instructions.

Example:
    from inventor_exporter.writers.mesh_converter import MeshConverter

    converter = MeshConverter(Path("output"), mesh_subdir="meshes")
    mesh_path = converter.convert(Path("part.step"), "part1")
    # Returns Path("meshes/part1.stl") - relative from output directory
"""

import logging
from pathlib import Path

# Attempt to import CadQuery
try:
    import cadquery as cq

    CADQUERY_AVAILABLE = True
except ImportError:
    CADQUERY_AVAILABLE = False

logger = logging.getLogger(__name__)


def convert_step_to_stl(
    step_path: Path,
    stl_path: Path,
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> None:
    """Convert STEP file to binary STL.

    Args:
        step_path: Input STEP file path.
        stl_path: Output STL file path.
        tolerance: Linear deflection (mm). Lower = finer mesh. Default 0.1.
        angular_tolerance: Angular deflection (radians). Lower = smoother curves.
            Default 0.1.

    Raises:
        RuntimeError: If CadQuery is not installed.
        FileNotFoundError: If STEP file does not exist.
        ValueError: If STEP file cannot be imported.
    """
    if not CADQUERY_AVAILABLE:
        raise RuntimeError(
            "cadquery is required for mesh conversion. "
            "Install with: pip install cadquery"
        )

    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    logger.debug("Converting %s to %s", step_path, stl_path)

    try:
        shape = cq.importers.importStep(str(step_path))
    except Exception as e:
        raise ValueError(f"Failed to import STEP file {step_path}: {e}") from e

    # Ensure parent directory exists
    stl_path.parent.mkdir(parents=True, exist_ok=True)

    # Export as binary STL (not ASCII - smaller files)
    cq.exporters.export(
        shape,
        str(stl_path),
        exportType="STL",
        tolerance=tolerance,
        angularTolerance=angular_tolerance,
    )

    logger.debug("Conversion complete: %s", stl_path)


class MeshConverter:
    """Batch STEP to STL converter with path management.

    Handles mesh file organization for robot description format writers.
    Creates a mesh subdirectory and tracks converted files for caching.

    Attributes:
        output_dir: Base output directory for the export.
        mesh_subdir: Name of the mesh subdirectory (default "meshes").

    Example:
        converter = MeshConverter(Path("output"), mesh_subdir="meshes")

        # Convert a STEP file
        rel_path = converter.convert(Path("parts/part1.step"), "part1")
        # Returns Path("meshes/part1.stl")

        # Get relative path for XML reference
        xml_path = converter.get_mesh_path("part1")
        # Returns Path("meshes/part1.stl")
    """

    def __init__(self, output_dir: Path, mesh_subdir: str = "meshes"):
        """Initialize mesh converter.

        Args:
            output_dir: Base directory for export output.
            mesh_subdir: Name of subdirectory for mesh files. Default "meshes".
        """
        self._output_dir = output_dir
        self._mesh_subdir = mesh_subdir
        self._converted: dict[str, Path] = {}  # mesh_name -> absolute stl_path

    @property
    def output_dir(self) -> Path:
        """Base output directory."""
        return self._output_dir

    @property
    def mesh_subdir(self) -> str:
        """Mesh subdirectory name."""
        return self._mesh_subdir

    @property
    def mesh_dir(self) -> Path:
        """Absolute path to mesh directory."""
        return self._output_dir / self._mesh_subdir

    def convert(
        self,
        step_path: Path,
        mesh_name: str,
        tolerance: float = 0.1,
        angular_tolerance: float = 0.1,
    ) -> Path:
        """Convert STEP file to STL, returning relative path.

        Caches conversions - if mesh_name was already converted, returns
        the cached path without reconverting.

        Args:
            step_path: Input STEP file path.
            mesh_name: Name for the output mesh (without extension).
            tolerance: Linear deflection for mesh quality. Default 0.1.
            angular_tolerance: Angular deflection for mesh quality. Default 0.1.

        Returns:
            Relative path from output_dir to the STL file.
            Example: Path("meshes/part1.stl")

        Raises:
            RuntimeError: If CadQuery is not installed.
            FileNotFoundError: If STEP file does not exist.
            ValueError: If STEP file cannot be imported.
        """
        # Check cache first
        if mesh_name in self._converted:
            logger.debug("Using cached mesh: %s", mesh_name)
            return self.get_mesh_path(mesh_name)

        # Compute paths
        stl_filename = f"{mesh_name}.stl"
        stl_path = self.mesh_dir / stl_filename

        # Skip conversion if STL already exists on disk
        if stl_path.exists():
            logger.debug("STL already exists, skipping conversion: %s", stl_path)
            self._converted[mesh_name] = stl_path
            return self.get_mesh_path(mesh_name)

        # Perform conversion
        convert_step_to_stl(
            step_path,
            stl_path,
            tolerance=tolerance,
            angular_tolerance=angular_tolerance,
        )

        # Cache the result
        self._converted[mesh_name] = stl_path

        return self.get_mesh_path(mesh_name)

    def get_mesh_path(self, mesh_name: str) -> Path:
        """Get relative path for mesh reference in XML.

        Args:
            mesh_name: Name of the mesh (without extension).

        Returns:
            Relative path from output_dir to mesh file.
            Example: Path("meshes/part1.stl")
        """
        return Path(self._mesh_subdir) / f"{mesh_name}.stl"

    def clear_cache(self) -> None:
        """Clear the conversion cache.

        Useful if you want to force reconversion of previously converted meshes.
        """
        self._converted.clear()
