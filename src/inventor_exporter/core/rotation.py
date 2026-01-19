"""Rotation conversion utilities for Inventor Exporter.

Converts Inventor's 3x3 rotation matrices to various representations
required by export formats:
- ADAMS: ZXZ Euler angles (degrees)
- URDF: RPY/ZYX Euler angles (radians)  
- MuJoCo: Quaternions (w, x, y, z)

Uses scipy.spatial.transform.Rotation for robust handling of gimbal lock
and edge cases. The existing VBA code has division-by-zero bugs in rotation
math - this module avoids those issues.
"""

from scipy.spatial.transform import Rotation
import numpy as np
from typing import Tuple
from enum import Enum
import warnings
import logging

logger = logging.getLogger(__name__)


class EulerConvention(Enum):
    """
    Euler angle conventions for export formats.

    Note: scipy uses UPPERCASE for intrinsic (body-fixed) rotations,
    lowercase for extrinsic (space-fixed) rotations.
    """

    ADAMS_ZXZ = "ZXZ"  # ADAMS View Body 3-1-3 Euler angles
    URDF_RPY = "ZYX"  # URDF roll-pitch-yaw (extrinsic XYZ = intrinsic ZYX)


def rotation_to_euler(
    rotation_matrix: np.ndarray,
    convention: EulerConvention,
    degrees: bool = True,
) -> Tuple[float, float, float]:
    """
    Convert rotation matrix to Euler angles.

    Args:
        rotation_matrix: 3x3 rotation matrix
        convention: Target Euler angle convention
        degrees: If True, return degrees; if False, radians

    Returns:
        Tuple of (angle1, angle2, angle3) in specified convention

    Notes:
        scipy handles gimbal lock by issuing a warning and setting
        the third angle to zero. The rotation is still correct.
    """
    # scipy from_matrix handles non-orthogonal matrices gracefully
    # by finding the nearest valid rotation matrix
    r = Rotation.from_matrix(rotation_matrix)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        angles = r.as_euler(convention.value, degrees=degrees)

        if w and any("gimbal lock" in str(warning.message).lower() for warning in w):
            logger.warning(
                f"Gimbal lock detected for {convention.value} conversion. "
                "Third angle set to zero. Rotation is still correct."
            )

    return tuple(angles)


def rotation_to_quaternion(
    rotation_matrix: np.ndarray,
    scalar_first: bool = True,
    canonical: bool = True,
) -> Tuple[float, float, float, float]:
    """
    Convert rotation matrix to quaternion.

    Args:
        rotation_matrix: 3x3 rotation matrix
        scalar_first: If True, return (w, x, y, z); if False, (x, y, z, w)
        canonical: If True, ensure w >= 0 (unique representation)

    Returns:
        Quaternion as tuple

    Notes:
        MuJoCo uses scalar-first (w, x, y, z) convention.
        Quaternions have no gimbal lock issues.
    """
    r = Rotation.from_matrix(rotation_matrix)
    q = r.as_quat(canonical=canonical, scalar_first=scalar_first)
    return tuple(q)
