"""
Tests for edge cases, error handling, and robustness
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from bvd import IssueType, Severity, VersionDetector
from bvd.parsers.terraform import TerraformParser


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_file_handling(self):
        """Test handling of empty files"""
        detector = VersionDetector()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write("")  # Empty file
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])
            assert issues == []  # Should handle gracefully

        finally:
            temp_path.unlink()

    def test_malformed_terraform_content(self):
        """Test handling of malformed Terraform content"""
        detector = VersionDetector()

        malformed_content = """
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Missing closing brace
    }
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(malformed_content)
            temp_path = Path(f.name)

        try:
            # Should not crash, should handle parsing errors gracefully
            _issues = detector.detect_issues([temp_path])
            # May return empty list or partial results, but shouldn't crash

        finally:
            temp_path.unlink()

    def test_terraform_without_providers(self):
        """Test Terraform files without provider blocks"""
        detector = VersionDetector()

        terraform_content = """
resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])
            assert issues == []  # No providers, no issues

        finally:
            temp_path.unlink()

    def test_complex_terraform_structure(self):
        """Test complex Terraform with multiple blocks"""
        detector = VersionDetector()

        terraform_content = """
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "my-terraform-state"
    key    = "state"
    region = "us-west-2"
  }
}

terraform {
  # Another terraform block
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Should find unbound kubernetes version
            unbound_issues = [i for i in issues if i.issue_type == IssueType.UNBOUND_VERSION]
            assert len(unbound_issues) == 1
            assert "kubernetes" in unbound_issues[0].message

        finally:
            temp_path.unlink()

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

    def test_file_reading_errors(self):
        """Test handling of file reading errors"""
        detector = VersionDetector()

        # Test with non-existent file
        fake_path = Path("/non/existent/file.tf")

        # Should handle gracefully without crashing
        issues = detector.detect_issues([fake_path])
        assert issues == []

    def test_git_command_unavailable(self):
        """Test behavior when git command is not available"""
        detector = VersionDetector()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git command not found")

            # Should handle gracefully
            changed_files = detector.get_changed_files()
            assert changed_files == []

            # Should also handle in get_file_content_at_ref
            content = detector.get_file_content_at_ref(Path("test.tf"), "HEAD~1")
            assert content is None

    def test_unicode_content_handling(self):
        """Test handling of files with unicode content"""
        detector = VersionDetector()

        terraform_content = """
# Terraform configuration with unicode: éñüñü
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"  # Comment with unicode: ñ
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tf", delete=False, encoding="utf-8"
        ) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            # Should handle unicode content without issues
            issues = detector.detect_issues([temp_path])
            # Should work normally, finding AWS provider
            assert len(issues) == 0  # AWS has bound version

        finally:
            temp_path.unlink()

    def test_large_file_handling(self):
        """Test handling of large Terraform files"""
        detector = VersionDetector()

        # Create a large terraform file with many providers
        terraform_content = """
terraform {
  required_providers {
"""

        # Add 100 providers
        for i in range(100):
            terraform_content += f"""
    provider_{i} = {{
      source  = "hashicorp/provider_{i}"
      version = ">= {i}.0.0"
    }}
"""

        terraform_content += """
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            # Should handle large files without performance issues
            issues = detector.detect_issues([temp_path])

            # Should find 100 unbound version issues
            unbound_issues = [i for i in issues if i.issue_type == IssueType.UNBOUND_VERSION]
            assert len(unbound_issues) == 100

        finally:
            temp_path.unlink()


class TestConfigurationEdgeCases:
    """Test configuration edge cases"""

    def test_empty_config(self):
        """Test detector with empty configuration"""
        detector = VersionDetector({})

        # Should use default configuration
        assert detector.config is not None
        assert "rules" in detector.config

    def test_partial_config(self):
        """Test detector with partial configuration"""
        partial_config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.ERROR,
            }
        }

        detector = VersionDetector(partial_config)

        # Should merge with defaults
        assert detector.config["rules"][IssueType.MAJOR_VERSION_BUMP] == Severity.ERROR
        # Should have default values for missing keys
        assert "ignore_packages" in detector.config

    def test_invalid_severity_handling(self):
        """Test handling of invalid severity values"""
        # This tests the robustness of the configuration system
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
            },
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
            },
            "ignore_packages": [],
        }

        detector = VersionDetector(config)

        # Should work normally with valid config
        assert detector.config["rules"][IssueType.MAJOR_VERSION_BUMP] == Severity.CRITICAL

    def test_none_config_values(self):
        """Test handling of None values in configuration"""
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
            },
            "critical_packages": None,  # None value
            "ignore_packages": [],
        }

        detector = VersionDetector(config)

        # Should handle None values gracefully
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            # Should not crash with None critical_packages
            issues = detector.detect_issues([temp_path])
            assert len(issues) >= 1  # Should find unbound version

        finally:
            temp_path.unlink()


class TestParserEdgeCases:
    """Test parser-specific edge cases"""

    def test_parser_registration_duplicate(self):
        """Test registering the same parser twice"""
        detector = VersionDetector()
        initial_count = len(detector.parsers)

        # Register terraform parser again
        terraform_parser = TerraformParser()
        detector.register_parser(terraform_parser)

        # Should replace, not duplicate
        assert len(detector.parsers) == initial_count

    def test_file_matching_edge_cases(self):
        """Test file pattern matching edge cases"""
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
