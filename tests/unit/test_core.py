"""
Tests for core BVD functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from bvd import IssueType, Severity, VersionDetector
from bvd.core import Issue, VersionChange


def test_version_detector():
    """Test basic detector functionality"""
    detector = VersionDetector()

    # Should have terraform parser registered
    assert "Terraform" in detector.parsers

    print("✅ Version detector tests passed")


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
        assert issues[0].issue_type == IssueType.UNBOUND_VERSION
        # hashicorp/aws is in critical_packages, so severity is CRITICAL
        assert issues[0].severity == Severity.CRITICAL

        print("✅ Issue detection tests passed")

    finally:
        temp_path.unlink()


def test_detect_issues_no_matching_parser():
    """Test issue detection when no parser matches file"""
    detector = VersionDetector()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".unknown", delete=False) as f:
        f.write("some unknown content")
        temp_path = Path(f.name)

    try:
        issues = detector.detect_issues([temp_path])

        # Should find no issues since no parser matches
        assert len(issues) == 0

        print("✅ No matching parser tests passed")

    finally:
        temp_path.unlink()


def test_detect_issues_processing_error():
    """Test error handling during issue detection"""
    detector = VersionDetector()

    # Mock a parser that raises an exception
    mock_parser = MagicMock()
    mock_parser.supported_files = ["*.tf"]
    mock_parser.name = "ErrorParser"
    mock_parser.parse_dependencies.side_effect = Exception("Parse error")

    detector.parsers["ErrorParser"] = mock_parser

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write("terraform {}")
        temp_path = Path(f.name)

    try:
        # Should handle error gracefully and continue with other parsers
        issues = detector.detect_issues([temp_path])

        # Should still work with the real Terraform parser
        assert isinstance(issues, list)

        print("✅ Error handling tests passed")

    finally:
        temp_path.unlink()


def test_version_detector_custom_config_merge():
    """Test that custom config merges properly with defaults"""
    custom_config = {
        "rules": {IssueType.UNBOUND_VERSION: Severity.WARNING},  # Override default ERROR
        "critical_packages": {"my/package": Severity.CRITICAL},  # Replaces defaults
        "ignore_packages": ["ignore/me"],  # Sets ignore list
    }

    detector = VersionDetector(config=custom_config)

    # Rules should merge with defaults
    expected_severity = detector.config["rules"][IssueType.UNBOUND_VERSION]
    assert expected_severity == Severity.WARNING
    # Other rules should remain from defaults
    assert detector.config["rules"][IssueType.MAJOR_VERSION_BUMP] == Severity.CRITICAL

    # Critical packages should be replaced (not merged)
    critical_packages = detector.config["critical_packages"]
    assert "hashicorp/aws" not in critical_packages  # Default replaced
    assert "my/package" in critical_packages  # Custom

    # Ignore packages should be set
    assert detector.config["ignore_packages"] == ["ignore/me"]

    print("✅ Config merge tests passed")


def test_issue_suggestions_formatting():
    """Test that issue suggestions are properly formatted"""
    change = VersionChange(
        package_name="hashicorp/aws",
        old_version=None,
        new_version="4.0.0",
        old_constraint=None,
        new_constraint=">= 4.0.0",
        file_path="test.tf",
    )

    suggestion = "Consider using '~> 4.0.0' to bound to major version"
    issue = Issue(
        severity=Severity.ERROR,
        issue_type=IssueType.UNBOUND_VERSION,
        message="Unbound version constraint found",
        change=change,
        suggestion=suggestion,
    )

    # Test string representation includes suggestions
    issue_str = str(issue)
    assert "suggestion=" in issue_str
    assert "Consider using" in issue_str

    # Test that suggestion field is properly set
    assert issue.suggestion == suggestion
    assert "~> 4.0.0" in issue.suggestion

    print("✅ Issue suggestions tests passed")


def test_detect_issues_exception_handling():
    """Test exception handling during file processing (coverage completion)"""
    import sys
    from io import StringIO

    detector = VersionDetector()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
        f.write("terraform {}")
        temp_path = Path(f.name)

    try:
        # Capture stderr to verify error message is printed
        old_stderr = sys.stderr
        captured_stderr = StringIO()
        sys.stderr = captured_stderr

        # Mock get_dependency_changes to raise an exception
        with patch.object(
            detector, "get_dependency_changes", side_effect=Exception("Test exception")
        ):
            issues = detector.detect_issues([temp_path])

            # Should handle exception gracefully and return empty list
            assert isinstance(issues, list)

            # Verify error was printed to stderr
            error_output = captured_stderr.getvalue()
            assert "Error processing" in error_output
            assert "Test exception" in error_output
            assert str(temp_path) in error_output

        print("✅ Exception handling tests passed")

    finally:
        sys.stderr = old_stderr
        temp_path.unlink()


