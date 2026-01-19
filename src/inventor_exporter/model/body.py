"""Body dataclass representing a rigid body in the assembly.

A Body composes the foundation types (Transform, Material reference, Inertia)
into a complete representation of a single rigid body in the assembly.
Bodies are the primary elements of the intermediate representation that
format writers iterate over.

The Body stores:
- name: Unique identifier (sanitized to remove problematic characters)
- transform: Pose in world frame
- material_name: Reference to a material in the assembly's material library
- inertia: Optional mass properties
- geometry_file: Optional path to exported STEP geometry
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from inventor_exporter.model.inertia import Inertia
from inventor_exporter.model.transform import Transform


@dataclass(frozen=True)
class Body:
    """A rigid body in the assembly.

    Attributes:
        name: Unique identifier for the body. Colons and spaces are
            automatically replaced with underscores during construction
            (Inventor uses colons in occurrence names which cause issues
            in some export formats).
        transform: Pose (position and orientation) in world frame.
        material_name: Reference to a material in AssemblyModel.materials.
            Validated at AssemblyModel level, not here.
        inertia: Optional mass properties. If provided, includes mass,
            center of mass, and inertia tensor.
        geometry_file: Optional path to exported geometry (e.g., STEP file).

    Examples:
        >>> from inventor_exporter.model import Transform
        >>> b = Body(name="link1", transform=Transform())
        >>> b.name
        'link1'

        >>> b2 = Body(name="Part:1 Name", transform=Transform())
        >>> b2.name
        'Part_1_Name'
    """

    name: str
    transform: Transform
    material_name: Optional[str] = None
    inertia: Optional[Inertia] = None
    geometry_file: Optional[Path] = None

    def __post_init__(self) -> None:
        """Sanitize name and validate after initialization."""
        # Sanitize name: replace colons and spaces with underscores
        sanitized = self.name.replace(":", "_").replace(" ", "_")

        # Use object.__setattr__ since frozen=True prevents direct assignment
        object.__setattr__(self, "name", sanitized)

        # Validate name is not empty after sanitization
        if not self.name:
            raise ValueError("Body name cannot be empty")
