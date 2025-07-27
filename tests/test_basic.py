"""
Basic tests for BVD
"""

import tempfile
from pathlib import Path

from bvd import VersionDetector
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


def test_version_detector():
    """Test basic detector functionality"""
    detector = VersionDetector()

    # Should have terraform parser registered
    assert "Terraform" in detector.parsers

    print("✅ Version detector tests passed")


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


def test_issue_detection():
    """Test issue detection on a real file"""
    terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}
"""

    detector = VersionDetector()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)

    try:
        issues = detector.detect_issues([temp_path])

        # Should find 1 unbound version issue
        assert len(issues) == 1
        assert issues[0].issue_type.value == "unbound_version"
        assert "hashicorp/aws" in issues[0].message

        print("✅ Issue detection tests passed")

    finally:
        temp_path.unlink()


def test_detect_issues_no_matching_parser():
    """Test detect_issues with file that has no matching parser (coverage completion)"""
    detector = VersionDetector()

    # Create a file with extension that has no parser
    with tempfile.NamedTemporaryFile(mode="w", suffix=".unknown", delete=False) as f:
        f.write("some content")
        temp_path = Path(f.name)

    try:
        issues = detector.detect_issues([temp_path])
        # Should handle gracefully and return empty list
        assert issues == []

    finally:
        temp_path.unlink()


def test_detect_issues_processing_error():
    """Test detect_issues error handling during processing (coverage completion)"""
    from unittest.mock import patch
    
    detector = VersionDetector()

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
        # Mock get_dependency_changes to raise an exception
        with patch.object(detector, "get_dependency_changes") as mock_get_changes:
            mock_get_changes.side_effect = Exception("Test processing error")

            # Should handle the exception gracefully
            issues = detector.detect_issues([temp_path])
            assert issues == []

    finally:
        temp_path.unlink()


def test_version_detector_custom_config_merge():
    """Test configuration merging edge cases (coverage completion)"""
    from bvd import IssueType, Severity
    
    config = {
        "rules": {
            IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
        },
        "new_key": "new_value",  # Test non-rules key
    }

    detector = VersionDetector(config)

    # Should merge with defaults
    assert detector.config["rules"][IssueType.MAJOR_VERSION_BUMP] == Severity.CRITICAL
    assert detector.config["new_key"] == "new_value"
    assert "ignore_packages" in detector.config  # Default should still be there


def test_terraform_parser_complex_provider_structure():
    """Test terraform parser with complex provider configurations (coverage completion)"""
    parser = TerraformParser()

    # Test with provider list format
    terraform_content = """
terraform {
  required_providers = [
    {
      aws = {
        source  = "hashicorp/aws"
        version = "~> 4.0.0"
      }
    }
  ]
}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)

    try:
        changes = parser.parse_dependencies(temp_path, terraform_content)
        # Should handle list format correctly
        assert len(changes) == 1
        assert "hashicorp/aws" in changes[0].package_name

    finally:
        temp_path.unlink()


def test_issue_suggestions_formatting():
    """Test issue suggestion formatting for different cases (coverage completion)"""
    detector = VersionDetector()

    # Test wildcard constraint suggestion vs regular constraint suggestion
    terraform_content = """
terraform {
  required_providers {
    wildcard_provider = {
      source  = "example/wildcard"
      version = "*"
    }
    regular_provider = {
      source  = "example/regular"
      version = ">= 1.0.0"
    }
  }
}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write(terraform_content)
        temp_path = Path(f.name)

    try:
        issues = detector.detect_issues([temp_path])

        wildcard_issue = next(i for i in issues if "wildcard" in i.message)
        regular_issue = next(i for i in issues if "regular" in i.message)

        # Wildcard should have special forbidden message
        assert "Wildcard constraints are strictly forbidden" in wildcard_issue.suggestion

        # Regular unbound should have different suggestion
        assert "Consider using '~>" in regular_issue.suggestion
        assert "Wildcard constraints are strictly forbidden" not in regular_issue.suggestion

    finally:
        temp_path.unlink()


def test_terraform_parser_without_hcl2():
    """Test terraform parser behavior when hcl2 is not available (coverage completion)"""
    from unittest.mock import patch
    
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
    from unittest.mock import patch
    
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
    test_version_detector()
    test_terraform_file_parsing()
    test_issue_detection()
    test_detect_issues_no_matching_parser()
    test_detect_issues_processing_error()
    test_version_detector_custom_config_merge()
    test_terraform_parser_complex_provider_structure()
    test_issue_suggestions_formatting()
    test_terraform_parser_without_hcl2()
    print("\n🎉 All tests passed!")
