"""Mass property extraction from Inventor parts.

Uses ComponentDefinition.MassProperties to get mass, center of mass, and
the full 6-component inertia tensor via XYZMomentsOfInertia.

Units:
- Inventor mass: kg
- Inventor length: cm
- Inventor inertia: kg*cm^2
- Output mass: kg
- Output CoM: meters
- Output inertia: kg*m^2
"""

import logging
from typing import Any

import numpy as np

from inventor_exporter.core.units import InventorUnits
from inventor_exporter.model import Inertia

logger = logging.getLogger(__name__)

# Inertia conversion: kg*cm^2 to kg*m^2
# cm^2 = 0.0001 m^2
CM2_TO_M2 = 0.0001


def extract_mass_properties(part_definition: Any) -> Inertia:
    """Extract mass properties from an Inventor part definition.

    Reads mass, center of mass, and full inertia tensor from the part's
    MassProperties object. Converts all units to SI (kg, m, kg*m^2).

    Args:
        part_definition: Inventor PartComponentDefinition COM object

    Returns:
        Inertia dataclass with:
        - mass in kg
        - center_of_mass in meters
        - 3x3 symmetric inertia tensor in kg*m^2

    Note:
        XYZMomentsOfInertia in pywin32 returns a tuple containing
        (Ixx, Iyy, Izz, Ixy, Iyz, Ixz) - not ByRef parameters like in VBA.

        The inertia tensor returned is about the coordinate system origin,
        NOT about the center of mass. Use Inertia.at_point() to transform
        if needed.
    """
    mp = part_definition.MassProperties

    # Mass is already in kg
    mass = mp.Mass
    logger.debug(f"Mass: {mass} kg")

    # Center of mass - convert from cm to meters
    com = mp.CenterOfMass
    center_of_mass = np.array([
        InventorUnits.length_to_meters(com.X),
        InventorUnits.length_to_meters(com.Y),
        InventorUnits.length_to_meters(com.Z),
    ])
    logger.debug(f"Center of mass: {center_of_mass} m")

    # Inertia tensor components via XYZMomentsOfInertia
    # In pywin32, this returns a tuple (not ByRef like VBA)
    result = mp.XYZMomentsOfInertia()

    # Unpack the tuple: (Ixx, Iyy, Izz, Ixy, Iyz, Ixz) in kg*cm^2
    Ixx_cm2, Iyy_cm2, Izz_cm2, Ixy_cm2, Iyz_cm2, Ixz_cm2 = result

    # Convert from kg*cm^2 to kg*m^2
    Ixx = Ixx_cm2 * CM2_TO_M2
    Iyy = Iyy_cm2 * CM2_TO_M2
    Izz = Izz_cm2 * CM2_TO_M2
    Ixy = Ixy_cm2 * CM2_TO_M2
    Iyz = Iyz_cm2 * CM2_TO_M2
    Ixz = Ixz_cm2 * CM2_TO_M2

    logger.debug(
        f"Inertia (kg*m^2): Ixx={Ixx:.6f}, Iyy={Iyy:.6f}, Izz={Izz:.6f}, "
        f"Ixy={Ixy:.6f}, Iyz={Iyz:.6f}, Ixz={Ixz:.6f}"
    )

    # Construct symmetric 3x3 inertia tensor
    # Layout:
    #   | Ixx  Ixy  Ixz |
    #   | Ixy  Iyy  Iyz |
    #   | Ixz  Iyz  Izz |
    inertia_tensor = np.array([
        [Ixx, Ixy, Ixz],
        [Ixy, Iyy, Iyz],
        [Ixz, Iyz, Izz],
    ])

    return Inertia(
        mass=mass,
        center_of_mass=center_of_mass,
        inertia_tensor=inertia_tensor,
    )
