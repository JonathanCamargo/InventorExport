"""Model package - intermediate representation dataclasses.

This package provides the data model for the intermediate representation (IR)
that captures assembly structure extracted from Inventor. All format writers
consume this common data model.

Dataclasses:
    Transform: 6-DOF pose (position + rotation)
    Material: Physical material properties (density, etc.)
    Inertia: Mass properties with tensor transformation methods
    Body: Rigid body composing transform, material, inertia, geometry
    AssemblyModel: Top-level container with validation
"""

from inventor_exporter.model.transform import Transform
from inventor_exporter.model.material import Material
from inventor_exporter.model.inertia import Inertia
from inventor_exporter.model.body import Body
from inventor_exporter.model.constraint import ConstraintInfo
from inventor_exporter.model.assembly import AssemblyModel
from inventor_exporter.model.kinematic_tree import (
    KinematicTree,
    classify_joints,
    get_joint_origin_in_child_frame,
    KINEMATIC_JOINT_TYPES,
)

__all__ = [
    "Transform",
    "Material",
    "Inertia",
    "Body",
    "ConstraintInfo",
    "AssemblyModel",
    "KinematicTree",
    "classify_joints",
    "get_joint_origin_in_child_frame",
    "KINEMATIC_JOINT_TYPES",
]
