"""
Tests for issue detection, critical packages, and ignore functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bvd import IssueType, Severity, VersionDetector


class TestCriticalPackageHandling:
    """Test critical package severity overrides"""

    def test_critical_package_unbound_version_severity(self):
        """Test that critical packages get upgraded severity for unbound versions"""
        config = {
            "rules": {
                IssueType.UNBOUND_VERSION: Severity.WARNING,
            },
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
            },
            "ignore_packages": [],
        }

        detector = VersionDetector(config)

        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            assert len(issues) == 2

            # AWS should have CRITICAL severity (upgraded from WARNING)
            aws_issue = next(i for i in issues if "hashicorp/aws" in i.message)
            assert aws_issue.severity == Severity.CRITICAL

            # Helm should have default WARNING severity
            helm_issue = next(i for i in issues if "hashicorp/helm" in i.message)
            assert helm_issue.severity == Severity.WARNING

        finally:
            temp_path.unlink()

    def test_critical_package_version_change_severity(self):
        """Test that critical packages get upgraded severity for version changes"""
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.ERROR,
            },
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
            },
            "ignore_packages": [],
        }

        detector = VersionDetector(config)

        old_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0.0"
    }
  }
}
"""

        new_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0.0"
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

                # Filter to only version change issues
                version_issues = [i for i in issues if i.issue_type == IssueType.MAJOR_VERSION_BUMP]
                assert len(version_issues) == 2

                # AWS should have CRITICAL severity (upgraded from ERROR)
                aws_issue = next(i for i in version_issues if "hashicorp/aws" in i.message)
                assert aws_issue.severity == Severity.CRITICAL

                # Helm should have default ERROR severity
                helm_issue = next(i for i in version_issues if "hashicorp/helm" in i.message)
                assert helm_issue.severity == Severity.ERROR

        finally:
            temp_path.unlink()


class TestIgnorePackageFunctionality:
    """Test package ignore functionality"""

    def test_ignore_packages_unbound_versions(self):
        """Test that ignored packages don't generate unbound version issues"""
        config = {
            "rules": {
                IssueType.UNBOUND_VERSION: Severity.ERROR,
            },
            "critical_packages": {},
            "ignore_packages": ["hashicorp/aws"],
        }

        detector = VersionDetector(config)

        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Should only find issue for helm, not aws
            assert len(issues) == 1
            assert "hashicorp/helm" in issues[0].message
            assert "hashicorp/aws" not in issues[0].message

        finally:
            temp_path.unlink()

    def test_ignore_packages_version_changes(self):
        """Test that ignored packages don't generate version change issues"""
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.ERROR,
            },
            "critical_packages": {},
            "ignore_packages": ["hashicorp/aws"],
        }

        detector = VersionDetector(config)

        old_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0.0"
    }
  }
}
"""

        new_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0.0"
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

                # Should only find issues for helm, not aws
                version_issues = [i for i in issues if i.issue_type == IssueType.MAJOR_VERSION_BUMP]
                assert len(version_issues) == 1
                assert "hashicorp/helm" in version_issues[0].message

        finally:
            temp_path.unlink()


class TestIssueDetectionIntegration:
    """Test complete issue detection workflow"""

    def test_detect_issues_complete_workflow(self):
        """Test full issue detection with all types of changes"""
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
                IssueType.MINOR_VERSION_BUMP: Severity.WARNING,
                IssueType.PATCH_VERSION_BUMP: Severity.INFO,
                IssueType.UNBOUND_VERSION: Severity.ERROR,
            },
            "critical_packages": {
                "hashicorp/kubernetes": Severity.CRITICAL,
            },
            "ignore_packages": ["hashicorp/local"],
        }

        detector = VersionDetector(config)

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
    local = {
      source  = "hashicorp/local"
      version = ">= 1.0.0"
    }
  }
}
"""

        new_content = """
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
    local = {
      source  = "hashicorp/local"
      version = ">= 2.0.0"
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

                # Should find:
                # 1. AWS major version bump (CRITICAL)
                # 2. Kubernetes minor version bump (CRITICAL due to critical package override)
                # 3. Helm unbound version (ERROR) - new dependency
                # Should NOT find local package issues (ignored)

                assert len(issues) == 3

                # Check AWS major version bump
                aws_issues = [
                    i
                    for i in issues
                    if "hashicorp/aws" in i.message and i.issue_type == IssueType.MAJOR_VERSION_BUMP
                ]
                assert len(aws_issues) == 1
                assert aws_issues[0].severity == Severity.CRITICAL

                # Check Kubernetes minor version bump (upgraded to CRITICAL)
                k8s_issues = [
                    i
                    for i in issues
                    if "hashicorp/kubernetes" in i.message
                    and i.issue_type == IssueType.MINOR_VERSION_BUMP
                ]
                assert len(k8s_issues) == 1
                assert k8s_issues[0].severity == Severity.CRITICAL

                # Check Helm unbound version
                helm_issues = [
                    i
                    for i in issues
                    if "hashicorp/helm" in i.message and i.issue_type == IssueType.UNBOUND_VERSION
                ]
                assert len(helm_issues) == 1
                assert helm_issues[0].severity == Severity.ERROR

                # Ensure no local package issues
                local_issues = [i for i in issues if "hashicorp/local" in i.message]
                assert len(local_issues) == 0

        finally:
            temp_path.unlink()

    def test_detect_issues_no_changes(self):
        """Test detection when no files have changed"""
        detector = VersionDetector()

        with patch.object(detector, "get_changed_files", return_value=[]):
            issues = detector.detect_issues()
            assert issues == []

    def test_detect_issues_with_base_ref(self):
        """Test that base_ref parameter is properly passed through"""
        detector = VersionDetector()

        with patch.object(detector, "get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = []

            detector.detect_issues(base_ref="HEAD~2")

            mock_get_changed.assert_called_once_with("HEAD~2")

    def test_issue_message_formatting(self):
        """Test that issue messages are properly formatted"""
        detector = VersionDetector()

        old_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.5.2"
    }
  }
}
"""

        new_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.1.0"
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

                version_issues = [i for i in issues if i.issue_type == IssueType.MAJOR_VERSION_BUMP]
                assert len(version_issues) == 1

                issue = version_issues[0]
                assert "Major Version Bump detected" in issue.message
                assert "hashicorp/aws changed from 4.5.2 to 5.1.0" in issue.message
                assert "Review breaking changes in hashicorp/aws changelog" in issue.suggestion
                assert "between versions 4.5.2 and 5.1.0" in issue.suggestion

        finally:
            temp_path.unlink()


class TestWildcardHandling:
    """Test proper handling of wildcard constraints"""

    def test_wildcard_constraint_forbidden(self):
        """Test that wildcard constraints get proper error message"""
        detector = VersionDetector()

        terraform_content = """
terraform {
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "*"
    }
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
            issues = detector.detect_issues([temp_path])

            # Should find 2 unbound version issues
            assert len(issues) == 2

            # Check wildcard issue has proper suggestion
            wildcard_issue = next(i for i in issues if "hashicorp/random" in i.message)
            assert wildcard_issue.issue_type == IssueType.UNBOUND_VERSION
            assert "Wildcard constraints are strictly forbidden" in wildcard_issue.suggestion
            # Should not suggest meaningless constraint
            assert "~> *" not in wildcard_issue.suggestion

            # Check regular unbound issue has different suggestion
            aws_issue = next(i for i in issues if "hashicorp/aws" in i.message)
            assert aws_issue.issue_type == IssueType.UNBOUND_VERSION
            assert "Consider using '~>" in aws_issue.suggestion
            assert "Wildcard constraints are strictly forbidden" not in aws_issue.suggestion

        finally:
            temp_path.unlink()


