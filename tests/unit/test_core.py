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

    finally:
        sys.stderr = old_stderr
        temp_path.unlink()


def test_analyze_version_change_downgrades():
    """Test that analyze_version_change correctly detects all types of downgrades"""
    detector = VersionDetector()

    # Test major version downgrades
    result = detector.analyze_version_change("2.0.0", "1.0.0")
    assert result == IssueType.MAJOR_VERSION_DOWNGRADE

    result = detector.analyze_version_change("3.2.1", "1.5.0")
    assert result == IssueType.MAJOR_VERSION_DOWNGRADE

    # Test minor version downgrades
    result = detector.analyze_version_change("1.5.0", "1.2.0")
    assert result == IssueType.MINOR_VERSION_DOWNGRADE

    result = detector.analyze_version_change("1.5.3", "1.2.1")
    assert result == IssueType.MINOR_VERSION_DOWNGRADE

    # Test patch version downgrades
    result = detector.analyze_version_change("1.2.5", "1.2.3")
    assert result == IssueType.PATCH_VERSION_DOWNGRADE

    result = detector.analyze_version_change("1.2.10", "1.2.1")
    assert result == IssueType.PATCH_VERSION_DOWNGRADE


def test_analyze_version_change_precedence():
    """Test that major changes take precedence over minor/patch"""
    detector = VersionDetector()

    # Major downgrade should take precedence over minor/patch differences
    result = detector.analyze_version_change("2.5.3", "1.0.0")
    assert result == IssueType.MAJOR_VERSION_DOWNGRADE

    result = detector.analyze_version_change("2.0.0", "1.8.9")
    assert result == IssueType.MAJOR_VERSION_DOWNGRADE

    # Minor downgrade should take precedence over patch differences
    result = detector.analyze_version_change("1.5.1", "1.2.9")
    assert result == IssueType.MINOR_VERSION_DOWNGRADE


def test_default_config_downgrade_severity():
    """Test that downgrades have correct default severity"""
    detector = VersionDetector()
    config = detector.config["rules"]

    # Major downgrades should be critical
    assert config[IssueType.MAJOR_VERSION_DOWNGRADE] == Severity.CRITICAL

    # Minor downgrades should be warning
    assert config[IssueType.MINOR_VERSION_DOWNGRADE] == Severity.WARNING

    # Patch downgrades should be warning (more severe than patch upgrades)
    assert config[IssueType.PATCH_VERSION_DOWNGRADE] == Severity.WARNING
    assert config[IssueType.PATCH_VERSION_BUMP] == Severity.INFO  # upgrades are less severe


def test_downgrade_issue_messages():
    """Test that downgrade issues have explicit messaging"""
    detector = VersionDetector()

    # Test major downgrade message
    change = VersionChange(
        package_name="test-package",
        old_version="2.0.0",
        new_version="1.0.0",
        old_constraint=None,
        new_constraint="= 1.0.0",
        file_path="test.tf",
    )

    issue = detector._create_version_change_issue(change)
    assert issue is not None
    assert issue.issue_type == IssueType.MAJOR_VERSION_DOWNGRADE
    assert "Major version downgrade detected" in issue.message
    assert "potential feature loss and security vulnerabilities" in issue.message
    assert "security implications" in issue.suggestion
    assert "removed features" in issue.suggestion

    # Test minor downgrade message
    change.old_version = "1.5.0"
    change.new_version = "1.2.0"
    issue = detector._create_version_change_issue(change)
    assert issue is not None
    assert issue.issue_type == IssueType.MINOR_VERSION_DOWNGRADE
    assert "Minor version downgrade detected" in issue.message
    assert "potential feature loss and missing bug fixes" in issue.message
    assert "removed features and bug fixes" in issue.suggestion

    # Test patch downgrade message
    change.old_version = "1.2.5"
    change.new_version = "1.2.3"
    issue = detector._create_version_change_issue(change)
    assert issue is not None
    assert issue.issue_type == IssueType.PATCH_VERSION_DOWNGRADE
    assert "Patch version downgrade detected" in issue.message
    assert "missing bug fixes and security patches" in issue.message
    assert "bug fixes and security patches" in issue.suggestion


def test_upgrade_messages_unchanged():
    """Test that upgrade messages are unchanged"""
    detector = VersionDetector()

    # Test major upgrade message (should be unchanged)
    change = VersionChange(
        package_name="test-package",
        old_version="1.0.0",
        new_version="2.0.0",
        old_constraint=None,
        new_constraint="= 2.0.0",
        file_path="test.tf",
    )

    issue = detector._create_version_change_issue(change)
    assert issue is not None
    assert issue.issue_type == IssueType.MAJOR_VERSION_BUMP
    assert "Major Version Bump detected" in issue.message
    assert "breaking changes" in issue.suggestion
    assert "changelog" in issue.suggestion
