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


def test_terraform_type_checking_imports():
    """Test TYPE_CHECKING import coverage in terraform parser"""

    # Test that TYPE_CHECKING is False at runtime
    from bvd.parsers.terraform import TYPE_CHECKING

    assert TYPE_CHECKING is False

    # Test forcing the TYPE_CHECKING import to be executed
    with patch("bvd.parsers.terraform.TYPE_CHECKING", True):
        import importlib

        import bvd.parsers.terraform

        importlib.reload(bvd.parsers.terraform)


if __name__ == "__main__":
    test_terraform_parser()
    test_terraform_file_parsing()
    test_terraform_parser_complex_provider_structure()
    test_terraform_parser_without_hcl2()
    test_terraform_type_checking_imports()
    print("\n🎉 All terraform parser tests passed!")
