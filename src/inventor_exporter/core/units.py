"""Unit conversion utilities for Inventor Exporter.

Autodesk Inventor ALWAYS uses these units internally regardless of document
display settings:
- Length: centimeters (cm)
- Angle: radians
- Mass: kilograms (kg)
- Time: seconds (s)

Source: https://help.autodesk.com/cloudhelp/2021/ENU/Inventor-API/files/UOM_Overview.htm
"""

from enum import Enum
from typing import NamedTuple


class LengthUnit(Enum):
    """Length units for conversion."""

    CENTIMETER = "cm"  # Inventor internal
    MILLIMETER = "mm"  # ADAMS default
    METER = "m"  # URDF/MuJoCo standard


class Position(NamedTuple):
    """3D position in specified units."""

    x: float
    y: float
    z: float


class InventorUnits:
    """
    Autodesk Inventor internal database units.

    Inventor ALWAYS uses these units internally regardless of document
    display settings:
    - Length: centimeters (cm)
    - Angle: radians
    - Mass: kilograms (kg)
    - Time: seconds (s)
    """

    # Conversion factors FROM Inventor internal units
    CM_TO_M = 0.01
    CM_TO_MM = 10.0
    RAD_TO_DEG = 57.29577951308232  # 180/pi

    @classmethod
    def length_to_meters(cls, value_cm: float) -> float:
        """Convert Inventor internal length (cm) to meters."""
        return value_cm * cls.CM_TO_M

    @classmethod
    def length_to_mm(cls, value_cm: float) -> float:
        """Convert Inventor internal length (cm) to millimeters."""
        return value_cm * cls.CM_TO_MM

    @classmethod
    def position_to_meters(cls, x: float, y: float, z: float) -> Position:
        """Convert Inventor position (cm) to meters."""
        return Position(
            x * cls.CM_TO_M,
            y * cls.CM_TO_M,
            z * cls.CM_TO_M,
        )

    @classmethod
    def position_to_mm(cls, x: float, y: float, z: float) -> Position:
        """Convert Inventor position (cm) to millimeters."""
        return Position(
            x * cls.CM_TO_MM,
            y * cls.CM_TO_MM,
            z * cls.CM_TO_MM,
        )

    @classmethod
    def angle_to_degrees(cls, value_rad: float) -> float:
        """Convert Inventor internal angle (radians) to degrees."""
        return value_rad * cls.RAD_TO_DEG
