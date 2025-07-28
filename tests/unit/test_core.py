"""
Tests for core BVD functionality
"""

import subprocess
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


class TestGitDiffFunctionality:
    """Test git diff related functionality"""

    def test_get_file_content_at_ref_success(self):
        """Test getting file content from git ref successfully"""
        detector = VersionDetector()

        # Mock successful git show command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="file content")

            result = detector.get_file_content_at_ref(Path("test.tf"), "HEAD~1")

            assert result == "file content"
            mock_run.assert_called_once_with(
                ["git", "show", "HEAD~1:test.tf"], capture_output=True, text=True, check=True
            )

    def test_get_file_content_at_ref_failure(self):
        """Test git show command failure"""
        detector = VersionDetector()

        # Mock failed git show command
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            result = detector.get_file_content_at_ref(Path("test.tf"), "HEAD~1")

            assert result is None

    def test_get_changed_files_success(self):
        """Test getting changed files from git diff"""
        detector = VersionDetector()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="file1.tf\nfile2.tf\n")

            # Mock Path.exists to return True
            with patch.object(Path, "exists", return_value=True):
                result = detector.get_changed_files("HEAD~1")

                assert len(result) == 2
                assert result[0].name == "file1.tf"
                assert result[1].name == "file2.tf"

    def test_get_changed_files_nonexistent_files(self):
        """Test that nonexistent files are filtered out"""
        detector = VersionDetector()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="existing.tf\ndeleted.tf\n")

            # Mock exists to return True only for existing.tf
            def mock_exists(self):
                return self.name == "existing.tf"

            with patch.object(Path, "exists", mock_exists):
                result = detector.get_changed_files("HEAD~1")

                assert len(result) == 1
                assert result[0].name == "existing.tf"

    def test_get_changed_files_git_error(self):
        """Test handling of git command errors"""
        detector = VersionDetector()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            result = detector.get_changed_files("HEAD~1")

            assert result == []


class TestDependencyChanges:
    """Test dependency change detection"""

    def setup_method(self):
        """Set up test data"""
        self.old_terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.0.0"
    }
  }
}
"""

        self.new_terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.1.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.0.0"
    }
  }
}
"""

    def test_get_dependency_changes_with_modifications(self):
        """Test detecting dependency changes between versions"""
        detector = VersionDetector()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(self.new_terraform_content)
            temp_path = Path(f.name)

        try:
            # Mock git show to return old content
            with patch.object(
                detector, "get_file_content_at_ref", return_value=self.old_terraform_content
            ):
                changes = detector.get_dependency_changes(temp_path, "HEAD~1")

                assert len(changes) == 3  # aws, kubernetes, helm

                # Check AWS version change
                aws_change = next(c for c in changes if "aws" in c.package_name)
                assert aws_change.old_version == "4.0.0"
                assert aws_change.new_version == "5.0.0"
                assert aws_change.old_constraint == "~> 4.0.0"
                assert aws_change.new_constraint == "~> 5.0.0"

                # Check Kubernetes version change
                k8s_change = next(c for c in changes if "kubernetes" in c.package_name)
                assert k8s_change.old_version == "2.0.0"
                assert k8s_change.new_version == "2.1.0"

                # Check Helm (new dependency)
                helm_change = next(c for c in changes if "helm" in c.package_name)
                assert helm_change.old_version is None  # New dependency
                assert helm_change.new_version == "2.0.0"

        finally:
            temp_path.unlink()

    def test_get_dependency_changes_new_file(self):
        """Test handling of completely new files"""
        detector = VersionDetector()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(self.new_terraform_content)
            temp_path = Path(f.name)

        try:
            # Mock git show to return None (file doesn't exist in old ref)
            with patch.object(detector, "get_file_content_at_ref", return_value=None):
                changes = detector.get_dependency_changes(temp_path, "HEAD~1")

                assert len(changes) == 3
                # All should be new dependencies
                for change in changes:
                    assert change.old_version is None
                    assert change.old_constraint is None

        finally:
            temp_path.unlink()

    def test_get_dependency_changes_no_parser(self):
        """Test handling files with no matching parser"""
        detector = VersionDetector()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".unknown", delete=False) as f:
            f.write("some content")
            temp_path = Path(f.name)

        try:
            changes = detector.get_dependency_changes(temp_path, "HEAD~1")
            assert changes == []

        finally:
            temp_path.unlink()

    def test_get_dependency_changes_parsing_error(self):
        """Test handling of parsing errors"""
        detector = VersionDetector()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write("invalid terraform content")
            temp_path = Path(f.name)

        try:
            with patch.object(
                detector, "get_file_content_at_ref", return_value="old invalid content"
            ):
                changes = detector.get_dependency_changes(temp_path, "HEAD~1")
                # Should handle error gracefully and return empty list
                assert changes == []

        finally:
            temp_path.unlink()


class TestVersionChangeAnalysis:
    """Test version change analysis logic"""

    def test_analyze_version_change_major_bump(self):
        """Test major version bump detection"""
        detector = VersionDetector()

        result = detector.analyze_version_change("1.0.0", "2.0.0")
        assert result == IssueType.MAJOR_VERSION_BUMP

        result = detector.analyze_version_change("1.5.3", "2.0.0")
        assert result == IssueType.MAJOR_VERSION_BUMP

    def test_analyze_version_change_minor_bump(self):
        """Test minor version bump detection"""
        detector = VersionDetector()

        result = detector.analyze_version_change("1.0.0", "1.1.0")
        assert result == IssueType.MINOR_VERSION_BUMP

        result = detector.analyze_version_change("2.5.0", "2.6.0")
        assert result == IssueType.MINOR_VERSION_BUMP

    def test_analyze_version_change_patch_bump(self):
        """Test patch version bump detection"""
        detector = VersionDetector()

        result = detector.analyze_version_change("1.0.0", "1.0.1")
        assert result == IssueType.PATCH_VERSION_BUMP

        result = detector.analyze_version_change("2.5.3", "2.5.4")
        assert result == IssueType.PATCH_VERSION_BUMP

    def test_analyze_version_change_no_change(self):
        """Test identical versions"""
        detector = VersionDetector()

        result = detector.analyze_version_change("1.0.0", "1.0.0")
        assert result is None

    def test_analyze_version_change_downgrade(self):
        """Test version downgrades"""
        detector = VersionDetector()

        result = detector.analyze_version_change("2.0.0", "1.0.0")
        assert result == IssueType.MAJOR_VERSION_DOWNGRADE  # Downgrades now trigger issues

    def test_analyze_version_change_invalid_versions(self):
        """Test handling of invalid version strings"""
        detector = VersionDetector()

        result = detector.analyze_version_change("invalid", "1.0.0")
        assert result is None

        result = detector.analyze_version_change("1.0.0", "invalid")
        assert result is None

        result = detector.analyze_version_change("invalid", "also-invalid")
        assert result is None

    def test_analyze_version_change_complex_versions(self):
        """Test complex version strings with pre-release tags"""
        detector = VersionDetector()

        result = detector.analyze_version_change("1.0.0-alpha", "2.0.0-beta")
        assert result == IssueType.MAJOR_VERSION_BUMP

        result = detector.analyze_version_change("1.0.0-rc1", "1.1.0")
        assert result == IssueType.MINOR_VERSION_BUMP


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
