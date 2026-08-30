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
        origin_world: Joint origin in assembly *world* coordinates (meters),
            read from the joint origin's geometry proxy (e.g. the centre of
            the circular edge the joint was placed on). Unambiguous — unlike
            ``origin``, it does not depend on knowing which occurrence's
            local frame the point belongs to. Prefer this when available.
        origin_two_world: Same for OriginTwo. For a solved rotational joint
            this lies on the same axis as ``origin_world``, possibly offset
            along it.
        origin_occurrence: Name of the occurrence whose local frame
            ``origin`` is expressed in. This is the occurrence that owns the
            joint origin *geometry*, which for a joint placed on a
            subassembly is a leaf part inside it, NOT ``occurrence_one``.
        origin_two_occurrence: Same for ``origin_two``.
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
    origin_world: Optional[tuple[float, float, float]] = None
    origin_two_world: Optional[tuple[float, float, float]] = None
    origin_occurrence: Optional[str] = None
    origin_two_occurrence: Optional[str] = None
    limits: Optional[tuple[float, float]] = None

    def world_origin(self) -> Optional[tuple[float, float, float]]:
        """Best available joint location in assembly world coords (meters).

        Falls back to OriginTwo's geometry when OriginOne's carries no
        on-axis point — a joint placed on a planar face or a sketch circle
        yields an axis but no centre. For a solved joint both origins lie on
        the joint axis, so either one places it correctly.

        Returns:
            World-frame point, or None if neither origin exposed one.
        """
        if self.origin_world is not None:
            return self.origin_world
        return self.origin_two_world
