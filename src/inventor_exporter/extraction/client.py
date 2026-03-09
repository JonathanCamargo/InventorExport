"""InventorClient - high-level extraction orchestrator.

Provides a single entry point for extracting complete assembly data from Inventor.
Combines assembly traversal, geometry export, material and mass extraction into
a validated AssemblyModel.

Example:
    from inventor_exporter.extraction import InventorClient
    from pathlib import Path

    client = InventorClient()
    model = client.extract_assembly(output_dir=Path("./output"))
    errors = model.validate()
    if errors:
        print("Validation errors:", errors)
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from inventor_exporter.core.com import inventor_app, active_assembly
from inventor_exporter.extraction.assembly import (
    traverse_assembly,
    traverse_assembly_recursive,
)
from inventor_exporter.extraction.constraints import extract_constraints_and_joints
from inventor_exporter.extraction.geometry import export_unique_parts
from inventor_exporter.extraction.material import extract_material
from inventor_exporter.extraction.mass import extract_mass_properties
from inventor_exporter.model import AssemblyModel, Body, ConstraintInfo, Material


logger = logging.getLogger(__name__)


class InventorClient:
    """High-level client for extracting assembly data from Inventor.

    Provides a single entry point that orchestrates all extraction operations:
    - Assembly traversal to find all leaf parts
    - STEP geometry export for unique parts
    - Material property extraction
    - Mass property extraction
    - Assembly model construction and validation

    The client handles COM lifecycle management and error recovery. If extraction
    fails for individual parts, the extraction continues with available data.

    Example:
        client = InventorClient()
        model = client.extract_assembly(output_dir=Path("./output"))
        errors = model.validate()
    """

    def __init__(self) -> None:
        """Initialize client. Does NOT connect to Inventor yet.

        The connection to Inventor is established only when extract_assembly()
        is called, using context managers for proper lifecycle management.
        """
        self._app: Any = None
        self._doc: Any = None
        self.logger = logging.getLogger(__name__)

    def extract_assembly(self, output_dir: Path) -> AssemblyModel:
        """Extract complete assembly data from the active Inventor document.

        This is the main entry point for extraction. It:
        1. Connects to running Inventor instance
        2. Traverses the active assembly for all leaf parts
        3. Exports STEP geometry for unique parts
        4. Extracts material properties
        5. Extracts mass properties
        6. Builds and validates the AssemblyModel

        Args:
            output_dir: Directory for STEP geometry output files

        Returns:
            AssemblyModel containing all bodies and materials, ready for
            format writers. The model is validated before return.

        Raises:
            InventorNotRunningError: If Inventor is not running
            NotAssemblyError: If no assembly document is active

        Note:
            Parts that fail extraction are logged and skipped. The returned
            model may have fewer bodies than the assembly has parts if some
            extractions failed.
        """
        with inventor_app() as app:
            with active_assembly(app) as doc:
                return self._extract_from_document(app, doc, output_dir)

    def _extract_from_document(
        self,
        app: Any,
        doc: Any,
        output_dir: Path,
    ) -> AssemblyModel:
        """Internal extraction logic operating on already-connected Inventor.

        Args:
            app: Inventor.Application COM object
            doc: AssemblyDocument COM object
            output_dir: Directory for STEP geometry output files

        Returns:
            Validated AssemblyModel
        """
        assembly_name = doc.DisplayName
        self.logger.info(f"Extracting assembly: {assembly_name}")

        # Step 1: Traverse assembly to get all leaf occurrences
        # Try recursive traversal first (handles nested subassemblies);
        # fall back to AllLeafOccurrences if recursion finds nothing.
        self.logger.info("Traversing assembly (recursive)...")
        occurrences = traverse_assembly_recursive(doc)
        if not occurrences:
            self.logger.info(
                "Recursive traversal found nothing, trying AllLeafOccurrences..."
            )
            occurrences = traverse_assembly(doc)
        self.logger.info(f"Found {len(occurrences)} leaf occurrences")

        if not occurrences:
            self.logger.warning("No leaf occurrences found in assembly")
            model = AssemblyModel(name=assembly_name)
            return model

        # Step 2: Export STEP geometry for unique parts
        self.logger.info("Exporting STEP geometry...")
        geometry_map: Dict[str, Path] = export_unique_parts(
            app, occurrences, output_dir
        )
        self.logger.info(f"Exported {len(geometry_map)} unique parts")

        # Step 3: Extract materials (deduplicated)
        self.logger.info("Extracting materials...")
        materials_dict: Dict[str, Material] = {}
        for occ in occurrences:
            try:
                material = extract_material(occ.part_document)
                if material is not None and material.name not in materials_dict:
                    materials_dict[material.name] = material
                    self.logger.debug(f"Added material: {material.name}")
            except Exception as e:
                self.logger.warning(
                    f"Failed to extract material for {occ.name}: {e}"
                )

        materials = tuple(materials_dict.values())
        self.logger.info(f"Extracted {len(materials)} unique materials")

        # Step 4: Build bodies
        self.logger.info("Building bodies...")
        bodies = []
        total = len(occurrences)

        for idx, occ in enumerate(occurrences, 1):
            try:
                body = self._build_body(occ, geometry_map, materials_dict)
                if body is not None:
                    bodies.append(body)
                self.logger.debug(f"Built body {idx}/{total}: {occ.name}")
            except Exception as e:
                self.logger.error(
                    f"Failed to build body for {occ.name}: {e}"
                )

        self.logger.info(f"Built {len(bodies)}/{total} bodies")

        # Step 5: Extract constraints and joints
        self.logger.info("Extracting constraints and joints...")
        asm_def = doc.ComponentDefinition
        constraint_infos: list[ConstraintInfo] = []
        try:
            constraint_infos = extract_constraints_and_joints(asm_def)
            self.logger.info(
                f"Extracted {len(constraint_infos)} constraints/joints"
            )
        except Exception as e:
            self.logger.warning(f"Failed to extract constraints: {e}")

        # Step 6: Build AssemblyModel
        model = AssemblyModel(
            name=assembly_name,
            bodies=tuple(bodies),
            materials=materials,
            constraints=tuple(constraint_infos),
        )

        # Step 7: Validate and return
        errors = model.validate()
        if errors:
            for error in errors:
                self.logger.warning(f"Validation error: {error}")
        else:
            self.logger.info("Model validation passed")

        return model

    def _build_body(
        self,
        occ: Any,
        geometry_map: Dict[str, Path],
        materials_dict: Dict[str, Material],
    ) -> Optional[Body]:
        """Build a Body from occurrence data.

        Args:
            occ: OccurrenceData with extracted occurrence info
            geometry_map: Mapping from definition_path to STEP file path
            materials_dict: Mapping from material name to Material object

        Returns:
            Body dataclass, or None if extraction fails
        """
        # Get STEP geometry path
        geometry_file = geometry_map.get(occ.definition_path)
        if geometry_file is None:
            self.logger.warning(
                f"No geometry for {occ.name} (definition: {occ.definition_path})"
            )

        # Extract material
        material_name: Optional[str] = None
        try:
            material = extract_material(occ.part_document)
            if material is not None:
                material_name = material.name
        except Exception as e:
            self.logger.warning(
                f"Failed to extract material for body {occ.name}: {e}"
            )

        # Extract mass properties
        inertia = None
        try:
            part_definition = occ.part_document.ComponentDefinition
            inertia = extract_mass_properties(part_definition)
        except Exception as e:
            self.logger.warning(
                f"Failed to extract mass properties for body {occ.name}: {e}"
            )

        return Body(
            name=occ.name,
            transform=occ.transformation,
            material_name=material_name,
            inertia=inertia,
            geometry_file=geometry_file,
        )
