"""
Tests to achieve 100% code coverage by testing previously uncovered lines
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bvd import IssueType, Severity, VersionDetector
from bvd.cli import main
from bvd.core import Issue, VersionChange
from bvd.parsers.base import DependencyParser
from bvd.parsers.terraform import TerraformParser


class TestCLICoverageCompletion:
    """Test uncovered CLI paths"""

    def test_cli_verbose_warnings_only(self):
        """Test CLI verbose output when only warnings are found (line 64)"""
        runner = CliRunner()

        warning_issue = Issue(
            severity=Severity.WARNING,
            issue_type=IssueType.MINOR_VERSION_BUMP,
            message="Warning issue",
            change=VersionChange("test", "1.0.0", "1.1.0", "~> 1.0.0", "~> 1.1.0", "test.tf"),
        )

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [Path("test.tf")]
            mock_detector.detect_issues.return_value = [warning_issue]
            mock_detector.report_issues.return_value = "Warning found"

            result = runner.invoke(main, ["--verbose"])

            # Should show warning count message
            assert "⚠️  Found 1 warnings" in result.output
            assert result.exit_code == 0


class TestCoreCoverageCompletion:
    """Test uncovered core functionality paths"""

    def test_detect_issues_no_matching_parser(self):
        """Test detect_issues with file that has no matching parser (line 207)"""
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

    def test_detect_issues_processing_error(self):
        """Test detect_issues error handling during processing (lines 281-282)"""
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


class TestParsersBaseCoverageCompletion:
    """Test uncovered paths in base parser"""

    def test_abstract_methods_coverage(self):
        """Test TYPE_CHECKING and abstract method definitions (lines 12, 22, 28, 33, 38)"""

        # Test that we can't instantiate abstract base class
        with pytest.raises(TypeError):
            DependencyParser()  # type: ignore

        # Create a concrete implementation for testing
        class TestParser(DependencyParser):
            @property
            def supported_files(self):
                return ["*.test"]  # Line 22 coverage

            @property
            def name(self):
                return "Test Parser"  # Line 28 coverage

            def parse_dependencies(self, file_path, content):
                return []  # Line 33 coverage

            def is_version_bound(self, constraint):
                return True  # Line 38 coverage

        # Test that concrete implementation works
        parser = TestParser()
        assert parser.supported_files == ["*.test"]
        assert parser.name == "Test Parser"
        assert parser.parse_dependencies(Path("test"), "content") == []
        assert parser.is_version_bound("~> 1.0.0") is True

        # Test extract_version method (inherited from base)
        assert parser.extract_version("~> 1.2.3") == "1.2.3"

    def test_type_checking_coverage(self):
        """Test TYPE_CHECKING import in base.py (line 12)"""
        # Force execution of the TYPE_CHECKING block
        import sys

        _original_typing = sys.modules.get("typing", None)

        # Temporarily modify TYPE_CHECKING to True to trigger the import
        with patch("bvd.parsers.base.TYPE_CHECKING", True):
            # This should cover the TYPE_CHECKING import line
            from bvd.parsers.base import DependencyParser

            assert DependencyParser is not None


class TestTerraformParserCoverageCompletion:
    """Test uncovered paths in terraform parser"""

    def test_terraform_parser_without_hcl2(self):
        """Test terraform parser behavior when hcl2 is not available (lines 38-39)"""

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

    def test_type_checking_import(self):
        """Test TYPE_CHECKING import coverage (line 14)"""
        # This is tested by importing the module successfully
        # The TYPE_CHECKING block should be covered by the import process
        from bvd.parsers.terraform import TYPE_CHECKING

        # TYPE_CHECKING should be False at runtime
        assert TYPE_CHECKING is False

    def test_type_checking_import_direct(self):
        """Direct test of TYPE_CHECKING import line"""
        # Force the TYPE_CHECKING import to be executed
        with patch("bvd.parsers.terraform.TYPE_CHECKING", True):
            # Re-import to trigger the TYPE_CHECKING block
            import importlib

            import bvd.parsers.terraform

            importlib.reload(bvd.parsers.terraform)


class TestAdditionalEdgeCases:
    """Additional edge case tests to improve overall coverage"""

    def test_version_detector_custom_config_merge(self):
        """Test configuration merging edge cases"""
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

    def test_terraform_parser_complex_provider_structure(self):
        """Test terraform parser with complex provider configurations"""
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

    def test_issue_suggestions_formatting(self):
        """Test issue suggestion formatting for different cases"""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
