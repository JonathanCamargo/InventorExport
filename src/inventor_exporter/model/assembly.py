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
from inventor_exporter.model.constraint import ConstraintInfo
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
    constraints: tuple[ConstraintInfo, ...] = field(default_factory=tuple)
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

    def occurrence_aliases(self) -> dict[str, list[str]]:
        """Map ancestor subassembly names to member body names.

        Inventor joints frequently reference a *subassembly* occurrence
        (e.g. ``Link1:1``) rather than the leaf parts inside it. This
        builds alias -> [body names] from each body's recorded ancestors,
        so kinematic constraints naming a subassembly can be resolved to
        the bodies underneath it.

        Returns:
            Dict mapping each ancestor name to the list of body names
            that live underneath it.
        """
        aliases: dict[str, list[str]] = {}
        for body in self.bodies:
            for ancestor in body.ancestors:
                aliases.setdefault(ancestor, []).append(body.name)
        return aliases

    def rigid_groups(
        self, occurrence_aliases: "dict[str, list[str]] | None" = None
    ) -> dict[str, list[str]]:
        """Compute groups of bodies rigidly connected by constraints/joints.

        Uses Union-Find over rigid constraints. Constraint occurrence names
        are sanitized the same way as Body.name (colons/spaces to underscores).

        Additionally, when a constraint references a *subassembly* name
        (via ``occurrence_aliases``), all leaf bodies underneath that
        subassembly are fused into one rigid unit — matching Inventor
        semantics where a joint on a subassembly moves its contents as
        one body. This is what turns joint references like ``Link1:1``
        into a single link made of many leaf parts.

        Args:
            occurrence_aliases: Precomputed aliases from
                ``occurrence_aliases()``. Computed if None.

        Returns:
            Dict mapping group representative name to list of body names.
            Every body appears in exactly one group; unconstrained bodies
            are in single-element groups. Fused subassembly groups use the
            subassembly's sanitized name as representative.
        """
        body_names = [b.name for b in self.bodies]
        parent = {n: n for n in body_names}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        body_name_set = set(body_names)
        for c in self.constraints:
            if not c.is_rigid:
                continue
            n1 = c.occurrence_one.replace(":", "_").replace(" ", "_")
            n2 = c.occurrence_two.replace(":", "_").replace(" ", "_")
            if n1 in body_name_set and n2 in body_name_set:
                union(n1, n2)

        # Fuse bodies under subassemblies that any constraint references:
        # the constraint names the subassembly, so its contents move as
        # one kinematic unit. The fused group is renamed to the alias
        # (subassembly name) so group naming reflects the mechanism link
        # rather than an arbitrary leaf part.
        if occurrence_aliases is None:
            occurrence_aliases = self.occurrence_aliases()
        if occurrence_aliases:
            referenced: set[str] = set()
            for c in self.constraints:
                referenced.add(c.occurrence_one.replace(":", "_").replace(" ", "_"))
                referenced.add(c.occurrence_two.replace(":", "_").replace(" ", "_"))
            for alias, members in occurrence_aliases.items():
                if alias in referenced and len(members) > 1:
                    for member in members[1:]:
                        union(members[0], member)
                    # Rename the fused group's representative to the alias
                    old_root = find(members[0])
                    if old_root != alias and old_root not in referenced:
                        parent[old_root] = alias
                        parent[alias] = alias

        groups_temp: dict[str, list[str]] = {}
        for name in body_names:
            root = find(name)
            groups_temp.setdefault(root, []).append(name)

        # Groups whose representative is a body must keep that body in the
        # group; rebuild with stable ordering (alias-named groups first).
        groups: dict[str, list[str]] = {}
        for root, members in groups_temp.items():
            if root in body_name_set:
                # Representative is a leaf body name: keep it as-is (single
                # bodies and constraint-fused groups)
                groups[root] = members
            else:
                # Alias-named group: keep
                groups[root] = members
        return groups

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
