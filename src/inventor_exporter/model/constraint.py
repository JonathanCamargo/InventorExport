"""Constraint and joint metadata from Inventor assembly.

Stores information about mechanical relationships between occurrences,
used for building kinematic trees and identifying rigid groups.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ConstraintInfo:
    """Assembly constraint or joint between two occurrences.

    Attributes:
        type: Constraint/joint type string. Constraints: "mate", "flush",
            "insert", "angle", "tangent". Joints: "rigid_joint",
            "rotational_joint", "slider_joint", "cylindrical_joint",
            "planar_joint", "ball_joint".
        occurrence_one: Name of first occurrence (as in Inventor).
        occurrence_two: Name of second occurrence.
        is_rigid: True if this removes all relative DOF between the parts.
        name: Inventor name for this constraint/joint.
        offset: Distance offset in meters (for mate/flush).
        angle: Angle in radians (for angle constraints).
        axis: Axis direction as (x, y, z) unit vector.
        origin: Origin point as (x, y, z) in meters.
        limits: (min, max) for joint limits.
    """

    type: str
    occurrence_one: str
    occurrence_two: str
    is_rigid: bool = False
    name: str = ""
    offset: Optional[float] = None
    angle: Optional[float] = None
    axis: Optional[tuple[float, float, float]] = None
    origin: Optional[tuple[float, float, float]] = None
    limits: Optional[tuple[float, float]] = None
