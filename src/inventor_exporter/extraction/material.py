"""Material property extraction from Inventor parts.

Reads material name and density from the ActiveMaterial's PhysicalPropertiesAsset.
Handles localization issues by searching for partial property name matches.

Units:
- Inventor density: kg/cm^3
- Output density: kg/m^3 (SI standard)
"""

import logging
from typing import Any, Optional

import win32com.client

from inventor_exporter.core.com import late_bind
from inventor_exporter.model import Material

logger = logging.getLogger(__name__)

# Density conversion: kg/cm^3 to kg/m^3
# 1 kg/cm^3 = 1,000,000 kg/m^3
CM3_TO_M3 = 1_000_000

# Default density (steel) in kg/m^3 for fallback
DEFAULT_DENSITY = 7800.0


def _get_asset_value(prop: Any) -> Optional[float]:
    """Extract numeric value from an AssetValue COM object.

    AssetValue is a base class - the actual value is on subclasses like
    FloatAssetValue. We try multiple access patterns for compatibility
    with different COM binding modes.

    Args:
        prop: AssetValue COM object

    Returns:
        Float value if accessible, None otherwise
    """
    # Method 1: Try direct Value access (works with late binding)
    try:
        return prop.Value
    except (AttributeError, TypeError):
        pass

    # Method 2: Try accessing via fresh late binding dispatch
    try:
        import win32com.client.dynamic
        import pythoncom
        late_prop = win32com.client.dynamic.Dispatch(prop._oleobj_)
        return late_prop.Value
    except Exception:
        pass

    # Method 3: Try casting to FloatAssetValue (early binding)
    try:
        float_prop = win32com.client.CastTo(prop, "FloatAssetValue")
        return float_prop.Value
    except Exception:
        pass

    # Method 4: Try get_Value method (some early binding styles)
    try:
        return prop.get_Value()
    except AttributeError:
        pass

    return None


def extract_material(part_doc: Any) -> Optional[Material]:
    """Extract material properties from an Inventor part document.

    Reads the active material's display name and density from the
    PhysicalPropertiesAsset. Handles localization by searching for
    property names containing "density" (English) or "dichte" (German).

    Args:
        part_doc: Inventor PartDocument COM object

    Returns:
        Material dataclass with name and density in kg/m^3, or None if
        no material is assigned to the part.

    Note:
        Property names vary by locale:
        - English: "Density", "Physical_Density"
        - German: "Dichte", "Physikalische_Dichte"
        Uses partial matching to handle all cases.
    """
    # Get the active material (use late binding to avoid gen_py cache issues)
    material = late_bind(part_doc.ActiveMaterial)
    if material is None:
        logger.warning(
            f"No material assigned to part: {part_doc.DisplayName}"
        )
        return None

    material_name = material.DisplayName
    logger.debug(f"Processing material: {material_name}")

    # Get physical properties asset (also use late binding)
    phys_props = late_bind(material.PhysicalPropertiesAsset)
    if phys_props is None:
        logger.warning(
            f"Material '{material_name}' has no PhysicalPropertiesAsset, "
            f"using default density {DEFAULT_DENSITY} kg/m^3"
        )
        return Material(name=material_name, density=DEFAULT_DENSITY)

    # Search for density property (handles localization)
    density_kg_m3: Optional[float] = None
    for i in range(1, phys_props.Count + 1):  # COM collections are 1-indexed
        prop = phys_props.Item(i)
        prop_name = prop.Name.lower()

        # Check for density-related property names
        if "density" in prop_name or "dichte" in prop_name:
            density_kg_cm3 = _get_asset_value(prop)
            if density_kg_cm3 is None:
                logger.warning(f"Could not read density value from '{prop.Name}'")
                continue

            density_kg_m3 = density_kg_cm3 * CM3_TO_M3
            logger.debug(
                f"Found density property '{prop.Name}': "
                f"{density_kg_cm3} kg/cm^3 = {density_kg_m3} kg/m^3"
            )
            break

    if density_kg_m3 is None:
        logger.warning(
            f"Density property not found for material '{material_name}', "
            f"using default density {DEFAULT_DENSITY} kg/m^3"
        )
        return Material(name=material_name, density=DEFAULT_DENSITY)

    return Material(name=material_name, density=density_kg_m3)
