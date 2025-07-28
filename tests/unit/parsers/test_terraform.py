"""
Tests for Terraform parser functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from bvd.parsers.terraform import TerraformParser


def test_terraform_parser():
    """Test basic Terraform parsing"""
    parser = TerraformParser()

    # Test unbound version detection
    assert not parser.is_version_bound(">= 1.0.0")
    assert not parser.is_version_bound("*")
    assert parser.is_version_bound("~> 1.0.0")
    assert parser.is_version_bound("= 1.0.0")

    print("✅ Terraform parser tests passed")


def test_terraform_file_parsing():
    """Test parsing a real Terraform file"""
    terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}
"""

    parser = TerraformParser()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)

    try:
        changes = parser.parse_dependencies(temp_path, terraform_content)

        # Should find 2 providers
        assert len(changes) == 2

        # Check AWS provider (unbound)
        aws_change = next(c for c in changes if "aws" in c.package_name)
        assert not parser.is_version_bound(aws_change.new_constraint)

        # Check Kubernetes provider (bound)
        k8s_change = next(c for c in changes if "kubernetes" in c.package_name)
        assert parser.is_version_bound(k8s_change.new_constraint)

        print("✅ Terraform file parsing tests passed")

    finally:
        temp_path.unlink()


def test_terraform_parser_complex_provider_structure():
    """Test complex Terraform provider structure parsing"""
    terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
      configuration_aliases = [aws.west]
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "aws" {
  alias  = "west"
  region = "us-west-2"
}
"""

    parser = TerraformParser()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)

    try:
        changes = parser.parse_dependencies(temp_path, terraform_content)

        # Should find 2 providers (provider blocks don't add new dependencies)
        assert len(changes) == 2

        provider_names = [c.package_name for c in changes]
        assert "hashicorp/aws" in provider_names
        assert "hashicorp/azurerm" in provider_names

        print("✅ Complex Terraform structure tests passed")

    finally:
        temp_path.unlink()


def test_terraform_parser_without_hcl2():
    """Test terraform parser behavior when hcl2 is not available (coverage completion)"""

    # Mock hcl2 as None to simulate it not being installed
    with patch("bvd.parsers.terraform.hcl2", None):
        parser = TerraformParser()

        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            # Should handle missing hcl2 gracefully and return empty list
            changes = parser.parse_dependencies(temp_path, terraform_content)
            assert changes == []

        finally:
            temp_path.unlink()


class TestTerraformParserEdgeCases:
    """Test Terraform parser edge cases"""

    def test_version_extraction_edge_cases(self):
        """Test version extraction with various constraint formats"""
        parser = TerraformParser()

        # Test various constraint formats
        test_cases = [
            ("~> 1.2.3", "1.2.3"),
            ("= 2.0.0", "2.0.0"),
            (">= 1.0.0, < 2.0.0", "1.0.0"),
            ("1.5.2", "1.5.2"),
            ("v1.2.3", "1.2.3"),
            ("1.0.0-alpha.1", "1.0.0-alpha.1"),
            ("~> 1.0", "1.0"),  # Valid incomplete semver format
            ("~> 1", "1"),  # Valid major-only version (normalized to 1.0.0)
            ("~> A.B.C", None),  # Invalid semver format
            ("~> #.@.!", None),  # Invalid characters
            ("latest", None),  # Non-version string
            ("", None),  # Empty string
        ]

        for constraint, expected in test_cases:
            result = parser.extract_version(constraint)
            assert result == expected, f"Failed for constraint '{constraint}'"

    def test_version_bound_detection_edge_cases(self):
        """Test version bound detection with edge cases"""
        parser = TerraformParser()

        bound_cases = [
            ("~> 1.0.0", True),
            ("~> 1.0", True),  # Incomplete version support
            ("~> 1", True),  # Major-only version support
            ("= 1.2.3", True),
            ("= 1.2", True),  # Incomplete version support
            ("1.2", True),  # Plain incomplete version
            ("~>1.0.0", True),  # No spaces
            ("  ~> 1.0.0  ", True),  # Extra whitespace
        ]

        unbound_cases = [
            (">= 1.0.0", False),
            ("> 1.0.0", False),
            ("*", False),
            ("  >= 1.0.0  ", False),  # With whitespace
            (">=1.0.0", False),  # No spaces
            ("", False),  # Empty string
        ]

        for constraint, expected in bound_cases:
            assert parser.is_version_bound(constraint) == expected, (
                f"Failed for bound case '{constraint}'"
            )

        for constraint, expected in unbound_cases:
            assert parser.is_version_bound(constraint) == expected, (
                f"Failed for unbound case '{constraint}'"
            )

    def test_parser_registration_duplicate(self):
        """Test registering the same parser twice"""
        from bvd import VersionDetector

        detector = VersionDetector()
        initial_count = len(detector.parsers)

        # Register terraform parser again
        terraform_parser = TerraformParser()
        detector.register_parser(terraform_parser)

        # Should replace, not duplicate
        assert len(detector.parsers) == initial_count

    def test_file_matching_edge_cases(self):
        """Test file pattern matching edge cases"""
        from bvd import VersionDetector

        detector = VersionDetector()

        test_cases = [
            ("main.tf", True),
            ("versions.tf", True),
            ("providers.tf", True),
            ("subdirectory/main.tf", True),
            ("main.tf.backup", False),
            ("terraform.tfvars", False),
            ("README.md", False),
        ]

        for filename, should_match in test_cases:
            path = Path(filename)
            parser = detector.find_matching_parser(path)

            if should_match:
                assert parser is not None, f"Should find parser for {filename}"
                assert parser.name == "Terraform"
            else:
                assert parser is None, f"Should not find parser for {filename}"
