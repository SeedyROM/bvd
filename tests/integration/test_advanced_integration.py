"""
Advanced integration tests for complex real-world scenarios
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bvd import IssueType, Severity, VersionDetector


class TestRealWorldScenarios:
    """Test realistic usage scenarios"""

    def test_multi_environment_terraform(self):
        """Test with multi-environment Terraform setup"""
        detector = VersionDetector()

        # Simulate dev environment
        dev_tf = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.67.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.23.0"
    }
  }
}

resource "aws_instance" "dev" {
  instance_type = "t2.micro"
}
"""

        # Simulate prod environment
        prod_tf = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.67.0"  # Same as dev for consistency
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.20.0"  # More flexible for prod
    }
  }
}

resource "aws_instance" "prod" {
  instance_type = "t3.large"
}
"""

        temp_files = []

        # Create dev.tf
        with tempfile.NamedTemporaryFile(mode="w", suffix="dev.tf", delete=False) as f:
            f.write(dev_tf)
            temp_files.append(Path(f.name))

        # Create prod.tf
        with tempfile.NamedTemporaryFile(mode="w", suffix="prod.tf", delete=False) as f:
            f.write(prod_tf)
            temp_files.append(Path(f.name))

        try:
            issues = detector.detect_issues(temp_files)

            # Should find unbound kubernetes version in prod.tf only
            unbound_issues = [i for i in issues if i.issue_type == IssueType.UNBOUND_VERSION]
            assert len(unbound_issues) == 1
            assert "kubernetes" in unbound_issues[0].message
            assert "prod.tf" in unbound_issues[0].change.file_path

        finally:
            for temp_file in temp_files:
                temp_file.unlink()

    def test_version_upgrade_simulation(self):
        """Test simulating a version upgrade across multiple files"""
        detector = VersionDetector()

        # Old state (before upgrade)
        old_versions_tf = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.60.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.20.0"
    }
  }
}
"""

        old_main_tf = """
terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.8.0"
    }
  }
}
"""

        # New state (after upgrade)
        new_versions_tf = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"  # Major version bump
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.24.0"  # Minor version bump
    }
  }
}
"""

        new_main_tf = """
terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.9.0"  # Patch version bump
    }
  }
}
"""

        temp_files = []

        # Create new state files
        with tempfile.NamedTemporaryFile(mode="w", suffix="versions.tf", delete=False) as f:
            f.write(new_versions_tf)
            temp_files.append(Path(f.name))

        with tempfile.NamedTemporaryFile(mode="w", suffix="main.tf", delete=False) as f:
            f.write(new_main_tf)
            temp_files.append(Path(f.name))

        try:
            # Mock git to return old content for both files
            def mock_get_file_content(file_path, ref):
                if "versions.tf" in str(file_path):
                    return old_versions_tf
                elif "main.tf" in str(file_path):
                    return old_main_tf
                return None

            with patch.object(
                detector, "get_file_content_at_ref", side_effect=mock_get_file_content
            ):
                issues = detector.detect_issues(temp_files, "HEAD~1")

                # Should detect all version changes
                major_bumps = [i for i in issues if i.issue_type == IssueType.MAJOR_VERSION_BUMP]
                minor_bumps = [i for i in issues if i.issue_type == IssueType.MINOR_VERSION_BUMP]
                patch_bumps = [i for i in issues if i.issue_type == IssueType.PATCH_VERSION_BUMP]

                assert len(major_bumps) == 1  # AWS
                assert len(minor_bumps) == 2  # Kubernetes and Helm
                assert len(patch_bumps) == 0  # Helm is minor, not patch

                # Verify specific changes
                aws_issue = next(i for i in major_bumps if "aws" in i.message)
                assert "4.60.0 to 5.0.0" in aws_issue.message

                k8s_issue = next(i for i in minor_bumps if "kubernetes" in i.message)
                assert "2.20.0 to 2.24.0" in k8s_issue.message

        finally:
            for temp_file in temp_files:
                temp_file.unlink()

    def test_configuration_driven_workflow_complete(self):
        """Test complete workflow with custom configuration"""
        custom_config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
                IssueType.MINOR_VERSION_BUMP: Severity.ERROR,
                IssueType.PATCH_VERSION_BUMP: Severity.WARNING,
                IssueType.UNBOUND_VERSION: Severity.CRITICAL,
            },
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
                "hashicorp/kubernetes": Severity.CRITICAL,
                "hashicorp/vault": Severity.ERROR,
            },
            "ignore_packages": ["hashicorp/random", "hashicorp/local", "hashicorp/null"],
        }

        detector = VersionDetector(custom_config)

        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"  # Unbound critical package
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "*"  # Wildcard critical package
    }
    vault = {
      source  = "hashicorp/vault"
      version = "> 3.0.0"  # Unbound regular critical package
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.0.0"  # Unbound regular package
    }
    random = {
      source  = "hashicorp/random"
      version = "*"  # Ignored package
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 1.0.0"  # Ignored package
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Should find 4 issues (not counting ignored packages)
            assert len(issues) == 4

            # All should be unbound version issues
            for issue in issues:
                assert issue.issue_type == IssueType.UNBOUND_VERSION

            # Check severity assignments
            severities = {issue.change.package_name: issue.severity for issue in issues}

            assert severities["hashicorp/aws"] == Severity.CRITICAL
            assert severities["hashicorp/kubernetes"] == Severity.CRITICAL
            assert severities["hashicorp/vault"] == Severity.ERROR
            assert (
                severities["hashicorp/helm"] == Severity.CRITICAL
            )  # Default unbound version severity

            # Check that ignored packages are not present
            package_names = [issue.change.package_name for issue in issues]
            assert "hashicorp/random" not in package_names
            assert "hashicorp/local" not in package_names

        finally:
            temp_path.unlink()


class TestReportFormatting:
    """Test advanced report formatting scenarios"""

    def test_comprehensive_json_report(self):
        """Test comprehensive JSON report with all issue types"""
        detector = VersionDetector()

        old_content = """
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

        new_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"  # Major version bump
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.1.0"  # Minor version bump
    }
    helm = {
      source  = "hashicorp/helm"
      version = "*"  # New unbound dependency
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(new_content)
            temp_path = Path(f.name)

        try:
            with patch.object(detector, "get_file_content_at_ref", return_value=old_content):
                issues = detector.detect_issues([temp_path])
                json_report = detector.report_issues(issues, "json")

                # Parse JSON to verify structure
                report_data = json.loads(json_report)
                assert isinstance(report_data, list)
                assert len(report_data) == 3

                # Verify all required fields are present
                for item in report_data:
                    required_fields = [
                        "severity",
                        "type",
                        "message",
                        "file",
                        "package",
                        "suggestion",
                    ]
                    for field in required_fields:
                        assert field in item

                # Verify issue types are present
                issue_types = {item["type"] for item in report_data}
                expected_types = {"major_version_bump", "minor_version_bump", "unbound_version"}
                assert issue_types == expected_types

                # Verify packages are correctly identified
                packages = {item["package"] for item in report_data}
                expected_packages = {"hashicorp/aws", "hashicorp/kubernetes", "hashicorp/helm"}
                assert packages == expected_packages

        finally:
            temp_path.unlink()

    def test_text_report_formatting_edge_cases(self):
        """Test text report formatting with edge cases"""
        detector = VersionDetector()

        terraform_content = """
terraform {
  required_providers {
    provider_with_special_chars = {
      source  = "example/provider-with-special-chars-symbols"
      version = "*"
    }
    very_long_provider_name_that_might_cause_formatting_issues = {
      source  = "example/very_long_provider_name_that_might_cause_formatting_issues_in_reports"
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
            text_report = detector.report_issues(issues, "text")

            # Should handle special characters and long names gracefully
            assert "provider-with-special-chars-symbols" in text_report
            assert (
                "very_long_provider_name_that_might_cause_formatting_issues_in_reports"
                in text_report
            )
            assert "ERROR:" in text_report or "CRITICAL:" in text_report
            assert "File:" in text_report
            assert "Package:" in text_report
            assert "Suggestion:" in text_report

            # Report should be well-formatted (no weird line breaks)
            lines = text_report.split("\n")
            for line in lines:
                # No line should be excessively long (reasonable formatting)
                if line.strip():
                    assert len(line) < 200

        finally:
            temp_path.unlink()


class TestGitIntegrationScenarios:
    """Test git integration edge cases"""

    def test_git_diff_with_renamed_files(self):
        """Test handling of renamed files in git diff"""
        detector = VersionDetector()

        # Mock git diff showing renamed files
        with patch.object(detector, "get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = [
                Path("new_name.tf"),  # File was renamed
                Path("other_file.tf"),
            ]

            # Mock file existence checks
            def mock_exists(self):
                return self.name in ["new_name.tf", "other_file.tf"]

            with patch.object(Path, "exists", mock_exists):
                # Should handle renamed files gracefully
                issues = detector.detect_issues()
                assert isinstance(issues, list)

    def test_git_diff_with_binary_files(self):
        """Test handling when git diff includes binary files"""
        detector = VersionDetector()

        # Create files with different extensions
        terraform_file = Path("config.tf")
        binary_file = Path("image.png")

        with patch.object(detector, "get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = [terraform_file, binary_file]

            with patch.object(detector, "find_matching_parser") as mock_find_parser:
                # Only terraform file should have a parser
                def mock_parser_finder(file_path):
                    if file_path.suffix == ".tf":
                        return detector.parsers["Terraform"]
                    return None

                mock_find_parser.side_effect = mock_parser_finder

                # Should skip binary files gracefully
                issues = detector.detect_issues()
                assert isinstance(issues, list)

    def test_git_history_edge_cases(self):
        """Test edge cases in git history handling"""
        detector = VersionDetector()

        test_cases = [
            ("HEAD~999", "Very old commit"),
            ("nonexistent-branch", "Non-existent branch"),
            ("", "Empty ref"),
            ("HEAD~1~1~1~1", "Complex ref"),
        ]

        for ref, description in test_cases:
            with patch.object(detector, "get_file_content_at_ref", return_value=None):
                with patch.object(detector, "get_changed_files", return_value=[]):
                    # Should handle various git ref formats gracefully
                    issues = detector.detect_issues(base_ref=ref)
                    assert isinstance(issues, list)


