"""Model package - intermediate representation dataclasses.

This package provides the data model for the intermediate representation (IR)
that captures assembly structure extracted from Inventor. All format writers
consume this common data model.

Foundation dataclasses:
    Transform: 6-DOF pose (position + rotation)
    Material: Physical material properties (density, etc.)
    Inertia: Mass properties with tensor transformation methods
"""

from inventor_exporter.model.transform import Transform
from inventor_exporter.model.material import Material
from inventor_exporter.model.inertia import Inertia

__all__ = [
    "Transform",
    "Material",
    "Inertia",
]
