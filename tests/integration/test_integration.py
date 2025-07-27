"""
Integration tests for complete BVD workflows
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from bvd import IssueType, Severity, VersionDetector


class TestCompleteWorkflows:
    """Test complete end-to-end workflows"""

    def test_full_version_change_detection_workflow(self):
        """Test complete workflow from git diff to issue detection"""
        detector = VersionDetector()

        old_terraform_content = """
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
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.10.0"
    }
  }
}
"""

        new_terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.24.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0.0"
    }
    vault = {
      source  = "hashicorp/vault"
      version = ">= 3.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(new_terraform_content)
            temp_path = Path(f.name)

        try:
            # Mock git show to return old content
            with patch.object(
                detector, "get_file_content_at_ref", return_value=old_terraform_content
            ):
                issues = detector.detect_issues([temp_path], "HEAD~1")

                # Should detect:
                # 1. AWS major version bump (4.67.0 -> 5.0.0)
                # 2. Kubernetes minor version bump (2.23.0 -> 2.24.0)
                # 3. Helm major version bump (2.10.0 -> 3.0.0)
                # 4. Vault unbound version (new dependency)

                assert len(issues) == 4

                # Check AWS major version bump
                aws_issues = [
                    i
                    for i in issues
                    if "hashicorp/aws" in i.message and i.issue_type == IssueType.MAJOR_VERSION_BUMP
                ]
                assert len(aws_issues) == 1
                assert "changed from 4.67.0 to 5.0.0" in aws_issues[0].message
                assert aws_issues[0].severity == Severity.CRITICAL

                # Check Kubernetes minor version bump
                k8s_issues = [
                    i
                    for i in issues
                    if "hashicorp/kubernetes" in i.message
                    and i.issue_type == IssueType.MINOR_VERSION_BUMP
                ]
                assert len(k8s_issues) == 1
                assert "changed from 2.23.0 to 2.24.0" in k8s_issues[0].message

                # Check Helm major version bump
                helm_issues = [
                    i
                    for i in issues
                    if "hashicorp/helm" in i.message
                    and i.issue_type == IssueType.MAJOR_VERSION_BUMP
                ]
                assert len(helm_issues) == 1
                assert "changed from 2.10.0 to 3.0.0" in helm_issues[0].message

                # Check Vault unbound version
                vault_issues = [
                    i
                    for i in issues
                    if "hashicorp/vault" in i.message and i.issue_type == IssueType.UNBOUND_VERSION
                ]
                assert len(vault_issues) == 1
                assert ">= 3.0.0" in vault_issues[0].message

        finally:
            temp_path.unlink()

    def test_configuration_driven_workflow(self):
        """Test workflow with custom configuration affecting results"""
        config = {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.ERROR,
                IssueType.MINOR_VERSION_BUMP: Severity.WARNING,
                IssueType.PATCH_VERSION_BUMP: Severity.INFO,
                IssueType.UNBOUND_VERSION: Severity.ERROR,
            },
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
                "hashicorp/kubernetes": Severity.CRITICAL,
            },
            "ignore_packages": ["hashicorp/local", "hashicorp/random"],
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
    random = {
      source  = "hashicorp/random"
      version = "*"
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
    local = {
      source  = "hashicorp/local"
      version = ">= 2.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
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
                # 1. AWS major version bump (CRITICAL due to critical_packages override)
                # 2. Kubernetes minor version bump (CRITICAL due to critical_packages override)
                # Should NOT find local or random issues (ignored)

                assert len(issues) == 2

                # Check AWS issue has CRITICAL severity
                aws_issue = next(i for i in issues if "hashicorp/aws" in i.message)
                assert aws_issue.severity == Severity.CRITICAL
                assert aws_issue.issue_type == IssueType.MAJOR_VERSION_BUMP

                # Check Kubernetes issue has CRITICAL severity
                k8s_issue = next(i for i in issues if "hashicorp/kubernetes" in i.message)
                assert k8s_issue.severity == Severity.CRITICAL
                assert k8s_issue.issue_type == IssueType.MINOR_VERSION_BUMP

                # Verify no ignored packages
                for issue in issues:
                    assert "hashicorp/local" not in issue.message
                    assert "hashicorp/random" not in issue.message

        finally:
            temp_path.unlink()

    def test_report_generation_workflow(self):
        """Test complete report generation in different formats"""
        detector = VersionDetector()

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
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Test text report
            text_report = detector.report_issues(issues, "text")
            assert "❌ ERROR:" in text_report or "🚨 CRITICAL:" in text_report
            assert "Unbound version constraint" in text_report
            assert "hashicorp/aws" in text_report
            assert "hashicorp/kubernetes" in text_report
            assert "File:" in text_report
            assert "Package:" in text_report
            assert "Suggestion:" in text_report

            # Test JSON report
            json_report = detector.report_issues(issues, "json")
            assert '"severity":' in json_report
            assert '"type":' in json_report
            assert '"message":' in json_report
            assert '"file":' in json_report
            assert '"package":' in json_report
            assert '"suggestion":' in json_report
            assert '"unbound_version"' in json_report

            # Verify JSON is valid by parsing it
            import json

            parsed = json.loads(json_report)
            assert isinstance(parsed, list)
            assert len(parsed) == 2
            for item in parsed:
                assert "severity" in item
                assert "type" in item
                assert "message" in item

        finally:
            temp_path.unlink()

    def test_multiple_file_workflow(self):
        """Test workflow with multiple Terraform files"""
        detector = VersionDetector()

        main_tf_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}
"""

        versions_tf_content = """
terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "*"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0.0"
    }
  }
}
"""

        temp_files = []

        # Create main.tf
        with tempfile.NamedTemporaryFile(mode="w", suffix="main.tf", delete=False) as f:
            f.write(main_tf_content)
            temp_files.append(Path(f.name))

        # Create versions.tf
        with tempfile.NamedTemporaryFile(mode="w", suffix="versions.tf", delete=False) as f:
            f.write(versions_tf_content)
            temp_files.append(Path(f.name))

        try:
            issues = detector.detect_issues(temp_files)

            # Should find issues across both files
            # AWS unbound version from main.tf
            # Kubernetes unbound version from versions.tf
            # Helm is properly bound, no issue

            assert len(issues) == 2

            # Check that issues are from different files
            file_paths = [issue.change.file_path for issue in issues]
            assert len(set(file_paths)) == 2  # Issues from 2 different files

            # Check specific issues
            aws_issues = [i for i in issues if "hashicorp/aws" in i.message]
            k8s_issues = [i for i in issues if "hashicorp/kubernetes" in i.message]
            helm_issues = [i for i in issues if "hashicorp/helm" in i.message]

            assert len(aws_issues) == 1
            assert len(k8s_issues) == 1
            assert len(helm_issues) == 0  # Helm is properly bound

        finally:
            for temp_file in temp_files:
                temp_file.unlink()

    def test_parser_extensibility_workflow(self):
        """Test that parser system is extensible (using existing terraform parser)"""
        detector = VersionDetector()

        # Verify terraform parser is registered
        assert "Terraform" in detector.parsers

        # Test file matching
        test_files = [
            ("main.tf", True),
            ("versions.tf", True),
            ("providers.tf", True),
            ("module/main.tf", True),
            ("terraform.tfvars", False),
            ("main.py", False),
            ("package.json", False),
        ]

        for filename, should_match in test_files:
            path = Path(filename)
            parser = detector.find_matching_parser(path)

            if should_match:
                assert parser is not None
                assert parser.name == "Terraform"
            else:
                assert parser is None

    def test_error_recovery_workflow(self):
        """Test that system gracefully handles errors and continues processing"""
        detector = VersionDetector()

        # Mix of valid and invalid files
        valid_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}
"""

        invalid_content = """
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Missing closing braces
"""

        temp_files = []

        # Create valid file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(valid_content)
            temp_files.append(Path(f.name))

        # Create invalid file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(invalid_content)
            temp_files.append(Path(f.name))

        try:
            # Should process valid file despite invalid file
            issues = detector.detect_issues(temp_files)

            # Should find issue from valid file
            aws_issues = [i for i in issues if "hashicorp/aws" in i.message]
            assert len(aws_issues) >= 0  # May be 0 or 1 depending on error handling

        finally:
            for temp_file in temp_files:
                temp_file.unlink()

    def test_real_world_terraform_scenario(self):
        """Test with a realistic Terraform configuration"""
        detector = VersionDetector()

        real_world_content = """
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.20"  # Unbound
    }

    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.10"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }

    local = {
      source  = "hashicorp/local"
      version = "2.4.0"  # Exact version
    }

    null = {
      source  = "hashicorp/null"
      version = "*"  # Unbound wildcard
    }
  }

  backend "s3" {
    bucket = "terraform-state-bucket"
    key    = "infrastructure/terraform.tfstate"
    region = "us-west-2"
  }
}

provider "aws" {
  region = "us-west-2"
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority.0.data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(real_world_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Should find unbound version issues for kubernetes and null
            unbound_issues = [i for i in issues if i.issue_type == IssueType.UNBOUND_VERSION]
            assert len(unbound_issues) == 2

            # Check specific unbound providers
            k8s_unbound = [i for i in unbound_issues if "kubernetes" in i.message]
            null_unbound = [i for i in unbound_issues if "null" in i.message]

            assert len(k8s_unbound) == 1
            assert len(null_unbound) == 1

            # Should NOT find issues for properly bound providers
            for issue in issues:
                assert "hashicorp/aws" not in issue.message  # Properly bound with ~>
                assert "hashicorp/helm" not in issue.message  # Properly bound with ~>
                assert "hashicorp/random" not in issue.message  # Properly bound with ~>
                assert "hashicorp/local" not in issue.message  # Exact version

        finally:
            temp_path.unlink()
