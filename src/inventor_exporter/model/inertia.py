"""Inertia dataclass for rigid body mass properties.

The Inertia class stores mass, center of mass, and inertia tensor for
a rigid body. It includes methods for transforming the inertia tensor
to different reference frames using the parallel axis theorem and
rotation matrices.

Units follow SI conventions:
- Mass: kg
- Center of mass: meters
- Inertia tensor: kg*m^2

The inertia tensor is always expressed at the center of mass position.
Use at_point() to compute the tensor at a different reference point.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _zero_vector() -> np.ndarray:
    """Create default zero center of mass vector."""
    return np.zeros(3)


def _zero_tensor() -> np.ndarray:
    """Create default zero inertia tensor."""
    return np.zeros((3, 3))


@dataclass(frozen=True)
class Inertia:
    """Mass properties of a rigid body.

    Attributes:
        mass: Total mass in kg. Must be non-negative.
        center_of_mass: Position of center of mass relative to body frame
            origin, in meters. Shape must be (3,).
        inertia_tensor: 3x3 symmetric inertia tensor at center of mass,
            in kg*m^2. Shape must be (3, 3).

    The inertia tensor is expressed at the center_of_mass position.
    To get the tensor at a different point (e.g., body origin), use
    the at_point() method which applies the parallel axis theorem.

    The class is immutable (frozen). Use rotated() to get a new Inertia
    instance with the tensor transformed to a different reference frame.

    Examples:
        >>> i = Inertia(mass=1.0)
        >>> i.mass
        1.0

        >>> import numpy as np
        >>> I_sphere = np.diag([0.4, 0.4, 0.4])  # Uniform sphere
        >>> inertia = Inertia(mass=1.0, inertia_tensor=I_sphere)
    """

    mass: float
    center_of_mass: np.ndarray = field(default_factory=_zero_vector)
    inertia_tensor: np.ndarray = field(default_factory=_zero_tensor)

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        if self.mass < 0:
            raise ValueError(f"mass must be non-negative, got {self.mass}")
        if self.center_of_mass.shape != (3,):
            raise ValueError(
                f"center_of_mass must be shape (3,), got {self.center_of_mass.shape}"
            )
        if self.inertia_tensor.shape != (3, 3):
            raise ValueError(
                f"inertia_tensor must be shape (3, 3), got {self.inertia_tensor.shape}"
            )

    def at_point(self, point: np.ndarray) -> np.ndarray:
        """Return inertia tensor transformed to a different reference point.

        Uses the parallel axis theorem (Steiner's theorem) to compute the
        inertia tensor about a different point than the center of mass.

        The parallel axis theorem states:
            I' = I + m * [(d.d)E - d @ d.T]

        where:
            - I is the inertia tensor at center of mass
            - m is the total mass
            - d is the displacement vector from CoM to new point
            - E is the 3x3 identity matrix
            - d.d is the dot product (scalar)
            - d @ d.T is the outer product (3x3 matrix)

        Args:
            point: The new reference point, in the same coordinate frame
                as center_of_mass. Shape must be (3,).

        Returns:
            3x3 inertia tensor expressed at the given point.

        Note:
            This method returns just the tensor (ndarray), not a new
            Inertia instance, since the tensor is no longer at CoM.
        """
        d = point - self.center_of_mass
        d_dot_d = np.dot(d, d)
        d_outer_d = np.outer(d, d)
        parallel_axis_term = self.mass * (d_dot_d * np.eye(3) - d_outer_d)
        return self.inertia_tensor + parallel_axis_term

    def rotated(self, R: np.ndarray) -> "Inertia":
        """Return a new Inertia with tensor rotated to a different frame.

        The inertia tensor transforms under rotation as:
            I' = R @ I @ R.T

        The center of mass also transforms:
            com' = R @ com

        Args:
            R: 3x3 rotation matrix representing the frame transformation.
                Must be orthonormal.

        Returns:
            New Inertia instance with transformed tensor and center of mass.
            Mass is unchanged.

        Examples:
            >>> import numpy as np
            >>> # 90 degree rotation about z-axis
            >>> R_z90 = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
            >>> I_ellipsoid = np.diag([1.0, 2.0, 3.0])
            >>> inertia = Inertia(mass=1.0, inertia_tensor=I_ellipsoid)
            >>> rotated = inertia.rotated(R_z90)
            >>> # Ixx and Iyy are swapped
        """
        new_tensor = R @ self.inertia_tensor @ R.T
        new_com = R @ self.center_of_mass
        return Inertia(
            mass=self.mass,
            center_of_mass=new_com,
            inertia_tensor=new_tensor,
        )
