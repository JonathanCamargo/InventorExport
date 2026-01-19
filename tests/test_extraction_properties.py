"""Tests for material and mass property extraction from Inventor.

Uses mocking to simulate COM objects since Inventor isn't available
during testing.
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, PropertyMock

from inventor_exporter.extraction.material import (
    extract_material,
    CM3_TO_M3,
    DEFAULT_DENSITY,
)
from inventor_exporter.extraction.mass import (
    extract_mass_properties,
    CM2_TO_M2,
)
from inventor_exporter.model import Material, Inertia


class TestExtractMaterial:
    """Tests for material extraction."""

    def test_extract_material_with_density(self):
        """Test extracting material with density property."""
        # Mock the property with density
        mock_prop = MagicMock()
        mock_prop.Name = "Physical_Density"
        mock_prop.Value = 0.00785  # kg/cm^3 for steel

        # Mock PhysicalPropertiesAsset
        mock_phys_props = MagicMock()
        mock_phys_props.Count = 1
        mock_phys_props.Item.return_value = mock_prop

        # Mock ActiveMaterial
        mock_material = MagicMock()
        mock_material.DisplayName = "Steel"
        mock_material.PhysicalPropertiesAsset = mock_phys_props

        # Mock part document
        mock_part_doc = MagicMock()
        mock_part_doc.ActiveMaterial = mock_material
        mock_part_doc.DisplayName = "TestPart"

        # Extract material
        result = extract_material(mock_part_doc)

        # Verify
        assert result is not None
        assert result.name == "Steel"
        # 0.00785 kg/cm^3 * 1,000,000 = 7850 kg/m^3
        assert result.density == pytest.approx(7850.0)

    def test_extract_material_handles_localization_german(self):
        """Test that German property name 'Dichte' is recognized."""
        # Mock the property with German name
        mock_prop = MagicMock()
        mock_prop.Name = "Physikalische_Dichte"
        mock_prop.Value = 0.0027  # kg/cm^3 for aluminum

        # Mock PhysicalPropertiesAsset
        mock_phys_props = MagicMock()
        mock_phys_props.Count = 1
        mock_phys_props.Item.return_value = mock_prop

        # Mock ActiveMaterial
        mock_material = MagicMock()
        mock_material.DisplayName = "Aluminium"
        mock_material.PhysicalPropertiesAsset = mock_phys_props

        # Mock part document
        mock_part_doc = MagicMock()
        mock_part_doc.ActiveMaterial = mock_material
        mock_part_doc.DisplayName = "TestPart"

        # Extract material
        result = extract_material(mock_part_doc)

        # Verify
        assert result is not None
        assert result.name == "Aluminium"
        # 0.0027 kg/cm^3 * 1,000,000 = 2700 kg/m^3
        assert result.density == pytest.approx(2700.0)

    def test_extract_material_no_material(self):
        """Test handling of part with no material assigned."""
        mock_part_doc = MagicMock()
        mock_part_doc.ActiveMaterial = None
        mock_part_doc.DisplayName = "NoMaterialPart"

        result = extract_material(mock_part_doc)

        assert result is None

    def test_extract_material_no_physical_properties(self):
        """Test handling of material without PhysicalPropertiesAsset."""
        # Mock ActiveMaterial without physical properties
        mock_material = MagicMock()
        mock_material.DisplayName = "CustomMaterial"
        mock_material.PhysicalPropertiesAsset = None

        # Mock part document
        mock_part_doc = MagicMock()
        mock_part_doc.ActiveMaterial = mock_material
        mock_part_doc.DisplayName = "TestPart"

        result = extract_material(mock_part_doc)

        # Should return material with default density
        assert result is not None
        assert result.name == "CustomMaterial"
        assert result.density == DEFAULT_DENSITY

    def test_extract_material_density_not_found(self):
        """Test handling when density property not found in asset."""
        # Mock a property that's not density
        mock_prop = MagicMock()
        mock_prop.Name = "YoungModulus"
        mock_prop.Value = 210e9

        # Mock PhysicalPropertiesAsset
        mock_phys_props = MagicMock()
        mock_phys_props.Count = 1
        mock_phys_props.Item.return_value = mock_prop

        # Mock ActiveMaterial
        mock_material = MagicMock()
        mock_material.DisplayName = "UnknownMaterial"
        mock_material.PhysicalPropertiesAsset = mock_phys_props

        # Mock part document
        mock_part_doc = MagicMock()
        mock_part_doc.ActiveMaterial = mock_material
        mock_part_doc.DisplayName = "TestPart"

        result = extract_material(mock_part_doc)

        # Should return material with default density
        assert result is not None
        assert result.name == "UnknownMaterial"
        assert result.density == DEFAULT_DENSITY

    def test_cm3_to_m3_constant(self):
        """Verify the unit conversion constant is correct."""
        assert CM3_TO_M3 == 1_000_000


class TestExtractMassProperties:
    """Tests for mass property extraction."""

    def test_extract_mass_properties_basic(self):
        """Test basic mass property extraction with unit conversion."""
        # Mock CenterOfMass point (in cm)
        mock_com = MagicMock()
        mock_com.X = 10.0  # cm
        mock_com.Y = 20.0  # cm
        mock_com.Z = 30.0  # cm

        # Mock MassProperties
        mock_mp = MagicMock()
        mock_mp.Mass = 1.5  # kg
        mock_mp.CenterOfMass = mock_com
        # XYZMomentsOfInertia returns tuple (Ixx, Iyy, Izz, Ixy, Iyz, Ixz) in kg*cm^2
        mock_mp.XYZMomentsOfInertia.return_value = (100.0, 200.0, 300.0, 10.0, 20.0, 30.0)

        # Mock part definition
        mock_part_def = MagicMock()
        mock_part_def.MassProperties = mock_mp

        # Extract mass properties
        result = extract_mass_properties(mock_part_def)

        # Verify type
        assert isinstance(result, Inertia)

        # Verify mass
        assert result.mass == 1.5

        # Verify center of mass converted to meters
        # 10 cm = 0.1 m, 20 cm = 0.2 m, 30 cm = 0.3 m
        np.testing.assert_array_almost_equal(
            result.center_of_mass,
            np.array([0.1, 0.2, 0.3])
        )

        # Verify inertia tensor diagonal converted to kg*m^2
        # 100 kg*cm^2 * 0.0001 = 0.01 kg*m^2
        assert result.inertia_tensor[0, 0] == pytest.approx(0.01)  # Ixx
        assert result.inertia_tensor[1, 1] == pytest.approx(0.02)  # Iyy
        assert result.inertia_tensor[2, 2] == pytest.approx(0.03)  # Izz

    def test_extract_mass_properties_symmetric_tensor(self):
        """Test that inertia tensor is symmetric."""
        # Mock CenterOfMass point
        mock_com = MagicMock()
        mock_com.X = 0.0
        mock_com.Y = 0.0
        mock_com.Z = 0.0

        # Mock MassProperties with off-diagonal terms
        mock_mp = MagicMock()
        mock_mp.Mass = 2.0
        mock_mp.CenterOfMass = mock_com
        # Return values with non-zero off-diagonal terms
        # (Ixx, Iyy, Izz, Ixy, Iyz, Ixz)
        mock_mp.XYZMomentsOfInertia.return_value = (1000.0, 2000.0, 3000.0, 150.0, 250.0, 350.0)

        mock_part_def = MagicMock()
        mock_part_def.MassProperties = mock_mp

        result = extract_mass_properties(mock_part_def)

        # Verify symmetry: tensor[i,j] == tensor[j,i]
        # Ixy at [0,1] and [1,0]
        assert result.inertia_tensor[0, 1] == result.inertia_tensor[1, 0]
        # Ixz at [0,2] and [2,0]
        assert result.inertia_tensor[0, 2] == result.inertia_tensor[2, 0]
        # Iyz at [1,2] and [2,1]
        assert result.inertia_tensor[1, 2] == result.inertia_tensor[2, 1]

        # Verify off-diagonal values are correct (converted)
        # 150 kg*cm^2 * 0.0001 = 0.015 kg*m^2
        assert result.inertia_tensor[0, 1] == pytest.approx(0.015)  # Ixy
        assert result.inertia_tensor[1, 2] == pytest.approx(0.025)  # Iyz
        assert result.inertia_tensor[0, 2] == pytest.approx(0.035)  # Ixz

    def test_extract_mass_properties_negative_products(self):
        """Test handling of negative products of inertia."""
        mock_com = MagicMock()
        mock_com.X = 0.0
        mock_com.Y = 0.0
        mock_com.Z = 0.0

        mock_mp = MagicMock()
        mock_mp.Mass = 1.0
        mock_mp.CenterOfMass = mock_com
        # Negative products of inertia are valid
        mock_mp.XYZMomentsOfInertia.return_value = (500.0, 500.0, 500.0, -100.0, -100.0, -100.0)

        mock_part_def = MagicMock()
        mock_part_def.MassProperties = mock_mp

        result = extract_mass_properties(mock_part_def)

        # Verify negative values are preserved
        assert result.inertia_tensor[0, 1] == pytest.approx(-0.01)  # Ixy
        assert result.inertia_tensor[1, 2] == pytest.approx(-0.01)  # Iyz
        assert result.inertia_tensor[0, 2] == pytest.approx(-0.01)  # Ixz

    def test_cm2_to_m2_constant(self):
        """Verify the inertia unit conversion constant is correct."""
        assert CM2_TO_M2 == 0.0001
