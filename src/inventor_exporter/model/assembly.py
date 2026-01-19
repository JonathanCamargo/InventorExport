"""AssemblyModel dataclass - the complete intermediate representation.

AssemblyModel is the top-level container for the intermediate representation (IR)
that format writers consume. It contains all bodies and materials in the assembly,
plus validation logic to ensure data integrity before export.

The validate() method performs comprehensive validation and returns ALL errors
found, not just the first one. This helps users fix multiple issues at once.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from inventor_exporter.model.body import Body
from inventor_exporter.model.material import Material


@dataclass(frozen=True)
class AssemblyModel:
    """Complete intermediate representation of an assembly.

    This is the top-level dataclass that format writers receive. It contains
    all bodies and materials needed to generate output in any format.

    Attributes:
        name: Assembly name (required, cannot be empty).
        bodies: Tuple of all rigid bodies in the assembly.
            Using tuple instead of list ensures true immutability.
        materials: Tuple of materials referenced by bodies.
        ground_body: Name of the ground/world/fixed body. Bodies may
            reference this for fixed joints. Default is "ground".

    Examples:
        >>> from inventor_exporter.model import Transform, Material, Body
        >>> steel = Material(name="steel", density=7800)
        >>> body = Body(name="link1", transform=Transform(), material_name="steel")
        >>> asm = AssemblyModel(name="Robot", bodies=(body,), materials=(steel,))
        >>> asm.validate()
        []
    """

    name: str
    bodies: tuple[Body, ...] = field(default_factory=tuple)
    materials: tuple[Material, ...] = field(default_factory=tuple)
    ground_body: str = "ground"

    def get_body(self, name: str) -> Optional[Body]:
        """Find a body by name.

        Args:
            name: The body name to search for.

        Returns:
            The Body with the given name, or None if not found.
        """
        for body in self.bodies:
            if body.name == name:
                return body
        return None

    def get_material(self, name: str) -> Optional[Material]:
        """Find a material by name.

        Args:
            name: The material name to search for.

        Returns:
            The Material with the given name, or None if not found.
        """
        for material in self.materials:
            if material.name == name:
                return material
        return None

    def validate(self) -> list[str]:
        """Validate the assembly model.

        Performs comprehensive validation and collects ALL errors found,
        not just the first one. This helps users fix multiple issues at once.

        Checks performed:
        1. Assembly name is not empty
        2. No duplicate body names
        3. All body material_name references exist in materials collection
        4. Bodies with inertia have positive mass
        5. Bodies with inertia have symmetric inertia tensor

        Returns:
            List of error messages. Empty list means the model is valid.

        Examples:
            >>> asm = AssemblyModel(name="")
            >>> errors = asm.validate()
            >>> "Assembly name is required" in errors
            True
        """
        errors: list[str] = []

        # 1. Assembly name is required
        if not self.name:
            errors.append("Assembly name is required")

        # 2. No duplicate body names
        body_names = [body.name for body in self.bodies]
        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in body_names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)
        if duplicates:
            errors.append(f"Duplicate body names: {duplicates}")

        # Build material name set for reference checking
        material_names = {m.name for m in self.materials}

        # Check each body
        for body in self.bodies:
            # 3. Material reference exists (if specified)
            if body.material_name is not None:
                if body.material_name not in material_names:
                    errors.append(
                        f"Body '{body.name}' references unknown material "
                        f"'{body.material_name}'"
                    )

            # 4 & 5. Inertia validation (if present)
            if body.inertia is not None:
                # 4. Positive mass
                if body.inertia.mass <= 0:
                    errors.append(
                        f"Body '{body.name}' has non-positive mass"
                    )

                # 5. Symmetric inertia tensor
                I = body.inertia.inertia_tensor
                if not np.allclose(I, I.T):
                    errors.append(
                        f"Body '{body.name}' has non-symmetric inertia tensor"
                    )

        return errors
