"""Transform dataclass for 6-DOF pose representation.

A Transform represents the complete spatial pose (position + orientation)
of a body in world coordinates. This is the standard representation used
throughout the intermediate representation for expressing where bodies
are located in 3D space.

Coordinate system: Right-handed, following Inventor conventions.
Units: Meters for position (converted from Inventor's internal cm).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _zero_position() -> np.ndarray:
    """Create default zero position vector."""
    return np.zeros(3)


def _identity_rotation() -> np.ndarray:
    """Create default identity rotation matrix."""
    return np.eye(3)


@dataclass(frozen=True)
class Transform:
    """6-DOF pose: position and orientation in world frame.

    Attributes:
        position: 3D position vector (x, y, z) in meters.
            Shape must be (3,).
        rotation: 3x3 rotation matrix representing orientation.
            Shape must be (3, 3). Must be orthonormal.

    The Transform is immutable (frozen) to ensure data integrity
    throughout the export pipeline. To create a new transform with
    different values, instantiate a new Transform object.

    Examples:
        >>> t = Transform()  # Identity transform at origin
        >>> t.position
        array([0., 0., 0.])

        >>> import numpy as np
        >>> t2 = Transform(position=np.array([1.0, 2.0, 3.0]))
        >>> t2.position[0]
        1.0
    """

    position: np.ndarray = field(default_factory=_zero_position)
    rotation: np.ndarray = field(default_factory=_identity_rotation)

    def __post_init__(self) -> None:
        """Validate field shapes after initialization."""
        if self.position.shape != (3,):
            raise ValueError(
                f"position must be shape (3,), got {self.position.shape}"
            )
        if self.rotation.shape != (3, 3):
            raise ValueError(
                f"rotation must be shape (3, 3), got {self.rotation.shape}"
            )
