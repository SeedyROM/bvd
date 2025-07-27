"""
Tests for git diff functionality and version change detection
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bvd import IssueType, VersionDetector


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
        assert result is None  # Downgrades don't trigger issues

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


