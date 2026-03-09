"""Material dataclass for physical material properties.

Materials identify the material assigned to a body. Mass and inertia
are computed directly by Inventor, so density is optional metadata.

Units follow SI conventions:
- Density: kg/m^3 (optional)
- Young's modulus: Pa (N/m^2)
- Poisson's ratio: dimensionless (0 to 0.5 typically)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Material:
    """Physical material properties.

    Attributes:
        name: Unique identifier for the material (e.g., "steel", "aluminum").
            Cannot be empty.
        density: Material density in kg/m^3. Optional — mass/inertia come
            directly from Inventor, not from density.
        youngs_modulus: Young's modulus (elastic modulus) in Pa.
            Optional, used by some simulation formats.
        poissons_ratio: Poisson's ratio (dimensionless).
            Optional, typically between 0 and 0.5.

    The Material is immutable (frozen) to ensure data integrity.

    Examples:
        >>> m = Material(name="steel", density=7800)
        >>> m.density
        7800

        >>> m2 = Material(name="aluminum")
    """

    name: str
    density: Optional[float] = None  # kg/m^3
    youngs_modulus: Optional[float] = None  # Pa
    poissons_ratio: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        if not self.name:
            raise ValueError("Material name cannot be empty")
        if self.density is not None and self.density <= 0:
            raise ValueError(
                f"density must be positive, got {self.density}"
            )
