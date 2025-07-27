"""
Tests for CLI functionality and parameter passing
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bvd import IssueType, Severity
from bvd.cli import check_file, main
from bvd.core import Issue, VersionChange


class TestCLIParameterPassing:
    """Test CLI parameter passing and functionality"""

    def test_main_with_base_ref_parameter(self):
        """Test that main CLI passes base-ref parameter correctly"""
        runner = CliRunner()

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [
                Path("test.tf")
            ]  # Need files to process
            mock_detector.detect_issues.return_value = []
            mock_detector.report_issues.return_value = ""

            result = runner.invoke(main, ["--base-ref", "HEAD~3"])

            # Should call detect_issues with the base_ref parameter
            mock_detector.detect_issues.assert_called_once_with(None, "HEAD~3")
            assert result.exit_code == 0

    def test_main_with_specific_files(self):
        """Test main CLI with specific files"""
        runner = CliRunner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write("terraform {}")
            temp_path = Path(f.name)

        try:
            with patch("bvd.cli.VersionDetector") as mock_detector_class:
                mock_detector = MagicMock()
                mock_detector_class.return_value = mock_detector
                mock_detector.detect_issues.return_value = []
                mock_detector.report_issues.return_value = ""

                result = runner.invoke(main, ["--files", str(temp_path), "--base-ref", "HEAD~2"])

                # Should call detect_issues with file paths and base_ref
                args, kwargs = mock_detector.detect_issues.call_args
                assert len(args[0]) == 1  # One file
                assert args[0][0].name == temp_path.name
                assert args[1] == "HEAD~2"  # base_ref
                assert result.exit_code == 0

        finally:
            temp_path.unlink()

    def test_main_with_verbose_output(self):
        """Test main CLI with verbose flag"""
        runner = CliRunner()

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [
                Path("test.tf")
            ]  # Need files to process
            mock_detector.detect_issues.return_value = []
            mock_detector.report_issues.return_value = ""

            result = runner.invoke(main, ["--verbose"])

            assert "Breaking Version Detector starting..." in result.output
            assert "No issues found!" in result.output
            assert result.exit_code == 0

    def test_main_exit_codes(self):
        """Test CLI exit codes for different scenarios"""
        runner = CliRunner()

        # Test exit code 1 for critical/error issues
        critical_issue = Issue(
            severity=Severity.CRITICAL,
            issue_type=IssueType.MAJOR_VERSION_BUMP,
            message="Critical issue",
            change=VersionChange("test", None, "2.0.0", None, "~> 2.0.0", "test.tf"),
        )

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [Path("test.tf")]
            mock_detector.detect_issues.return_value = [critical_issue]
            mock_detector.report_issues.return_value = "Critical issue found"

            result = runner.invoke(main, [])

            assert result.exit_code == 1
            assert "Critical issue found" in result.output

        # Test exit code 0 for warnings only
        warning_issue = Issue(
            severity=Severity.WARNING,
            issue_type=IssueType.MINOR_VERSION_BUMP,
            message="Warning issue",
            change=VersionChange("test", None, "1.1.0", None, "~> 1.1.0", "test.tf"),
        )

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [Path("test.tf")]
            mock_detector.detect_issues.return_value = [warning_issue]
            mock_detector.report_issues.return_value = "Warning issue found"

            result = runner.invoke(main, [])

            assert result.exit_code == 0
            assert "Warning issue found" in result.output

    def test_main_json_output_format(self):
        """Test CLI JSON output format"""
        runner = CliRunner()

        issue = Issue(
            severity=Severity.WARNING,
            issue_type=IssueType.UNBOUND_VERSION,
            message="Test issue",
            change=VersionChange("test/pkg", None, "1.0.0", None, ">= 1.0.0", "test.tf"),
        )

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [Path("test.tf")]
            mock_detector.detect_issues.return_value = [issue]
            mock_detector.report_issues.return_value = '{"test": "json"}'

            result = runner.invoke(main, ["--format", "json"])

            # Should call report_issues with json format
            mock_detector.report_issues.assert_called_once_with([issue], "json")
            assert '{"test": "json"}' in result.output
            assert result.exit_code == 0

    def test_main_no_changes_shows_help(self):
        """Test that CLI shows help when no files specified and no git changes"""
        runner = CliRunner()

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = []  # No changed files

            result = runner.invoke(main, [])

            # Should show help and exit with code 0
            assert "Usage:" in result.output
            assert result.exit_code == 0

    def test_check_file_command(self):
        """Test check_file command functionality"""
        runner = CliRunner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write("terraform {}")
            temp_path = Path(f.name)

        try:
            with patch("bvd.cli.VersionDetector") as mock_detector_class:
                mock_detector = MagicMock()
                mock_detector_class.return_value = mock_detector
                mock_detector.detect_issues.return_value = []
                mock_detector.report_issues.return_value = ""

                result = runner.invoke(check_file, [str(temp_path), "--base-ref", "HEAD~1"])

                # Should call detect_issues with file and base_ref
                args, kwargs = mock_detector.detect_issues.call_args
                assert len(args[0]) == 1
                assert args[0][0].name == temp_path.name
                assert args[1] == "HEAD~1"

                assert "No issues found!" in result.output
                assert result.exit_code == 0

        finally:
            temp_path.unlink()

    def test_check_file_with_issues(self):
        """Test check_file command with issues found"""
        runner = CliRunner()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write("terraform {}")
            temp_path = Path(f.name)

        try:
            issue = Issue(
                severity=Severity.ERROR,
                issue_type=IssueType.UNBOUND_VERSION,
                message="Test issue",
                change=VersionChange("test/pkg", None, "1.0.0", None, ">= 1.0.0", str(temp_path)),
            )

            with patch("bvd.cli.VersionDetector") as mock_detector_class:
                mock_detector = MagicMock()
                mock_detector_class.return_value = mock_detector
                mock_detector.detect_issues.return_value = [issue]
                mock_detector.report_issues.return_value = "Error found"

                result = runner.invoke(check_file, [str(temp_path)])

                assert "Error found" in result.output
                assert result.exit_code == 1

        finally:
            temp_path.unlink()

    def test_cli_error_handling(self):
        """Test CLI error handling"""
        runner = CliRunner()

        with patch("bvd.cli.VersionDetector") as mock_detector_class:
            mock_detector = MagicMock()
            mock_detector_class.return_value = mock_detector
            mock_detector.get_changed_files.return_value = [Path("test.tf")]
            mock_detector.detect_issues.side_effect = Exception("Test error")

            result = runner.invoke(main, [])

            assert "Error: Test error" in result.output
            assert result.exit_code == 1


class TestCLIIntegration:
    """Integration tests for CLI with real functionality"""

    def test_cli_end_to_end_text_output(self):
        """Test complete CLI workflow with text output"""
        runner = CliRunner()

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
            result = runner.invoke(main, ["--files", str(temp_path), "--format", "text"])

            # Should find unbound version issue
            assert "Unbound version constraint" in result.output
            assert "hashicorp/aws" in result.output
            assert result.exit_code == 1  # Error severity

        finally:
            temp_path.unlink()

    def test_cli_end_to_end_json_output(self):
        """Test complete CLI workflow with JSON output"""
        runner = CliRunner()

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
            result = runner.invoke(main, ["--files", str(temp_path), "--format", "json"])

            # Should return valid JSON
            assert '"severity":' in result.output
            assert '"type":' in result.output
            assert '"package":' in result.output
            assert result.exit_code == 1

        finally:
            temp_path.unlink()

    def test_cli_with_bound_versions_no_issues(self):
        """Test CLI with properly bound versions (no issues)"""
        runner = CliRunner()

        terraform_content = """
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            result = runner.invoke(main, ["--files", str(temp_path), "--verbose"])

            assert "No issues found!" in result.output
            assert result.exit_code == 0

        finally:
            temp_path.unlink()

    def test_cli_with_nonexistent_file(self):
        """Test CLI behavior with nonexistent file"""
        runner = CliRunner()

        result = runner.invoke(check_file, ["/nonexistent/file.tf"])

        # Click should handle file existence check
        assert result.exit_code != 0

    def test_cli_verbose_with_multiple_issues(self):
        """Test verbose output with multiple issues"""
        runner = CliRunner()

        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "*"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "> 2.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            result = runner.invoke(main, ["--files", str(temp_path), "--verbose"])

            assert "Breaking Version Detector starting..." in result.output
            assert "Found 3 critical/error issues" in result.output
            assert result.exit_code == 1

        finally:
            temp_path.unlink()

    def test_cli_verbose_warnings_only(self):
        """Test CLI verbose output when only warnings are found (coverage completion)"""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
