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
        axis: Axis direction as (x, y, z) unit vector (world coords).
        origin: Origin point as (x, y, z) in meters. From OriginOne.Point
            (OccurrenceOne's local frame) unless origin_source says otherwise.
        origin_two: Origin point from OriginTwo.Point (OccurrenceTwo's local
            frame) in meters. None if extraction failed.
        origin_source: Which origin ``origin`` came from: "OriginOne" or
            "OriginTwo". Matters when the spanning tree flips parent/child.
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
    origin_two: Optional[tuple[float, float, float]] = None
    origin_source: str = "OriginOne"
    limits: Optional[tuple[float, float]] = None
