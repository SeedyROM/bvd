"""
Performance and stress tests for BVD, not required but useful for ensuring robustness under load.
These tests cover large files, multiple files, and stress conditions.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from bvd import VersionDetector
from bvd.parsers.terraform import TerraformParser


class TestPerformance:
    """Test performance characteristics of BVD"""

    def test_large_terraform_file_processing(self):
        """Test processing of large Terraform files"""
        detector = VersionDetector()

        # Generate a large Terraform file with many providers
        terraform_content = "terraform {\n  required_providers {\n"

        # Add 500 providers to stress test
        for i in range(500):
            terraform_content += f"""
    provider_{i:03d} = {{
      source  = "example/provider_{i:03d}"
      version = ">= {i % 10}.{(i + 1) % 10}.{(i + 2) % 10}"
    }}
"""

        terraform_content += "  }\n}\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            start_time = time.time()
            issues = detector.detect_issues([temp_path])
            processing_time = time.time() - start_time

            # Should process large file in reasonable time (< 5 seconds)
            assert processing_time < 5.0, f"Processing took {processing_time:.2f}s, too slow"

            # Should find 500 unbound version issues
            assert len(issues) == 500

            # Verify all issues are unbound version issues
            for issue in issues:
                assert issue.issue_type.value == "unbound_version"

        finally:
            temp_path.unlink()

    def test_multiple_files_processing_performance(self):
        """Test performance with multiple files"""
        detector = VersionDetector()

        temp_files = []

        # Create 50 smaller Terraform files
        for file_idx in range(50):
            terraform_content = f"""
terraform {{
  required_providers {{
    aws_{file_idx} = {{
      source  = "hashicorp/aws"
      version = ">= {file_idx % 5}.0.0"
    }}
    kubernetes_{file_idx} = {{
      source  = "hashicorp/kubernetes"
      version = "~> {file_idx % 3}.0.0"
    }}
  }}
}}
"""
            with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{file_idx}.tf", delete=False) as f:
                f.write(terraform_content)
                temp_files.append(Path(f.name))

        try:
            start_time = time.time()
            issues = detector.detect_issues(temp_files)
            processing_time = time.time() - start_time

            # Should process 50 files in reasonable time (< 10 seconds)
            assert processing_time < 10.0

            # Should find 50 unbound version issues (one aws per file)
            unbound_issues = [i for i in issues if i.issue_type.value == "unbound_version"]
            assert len(unbound_issues) == 50

        finally:
            for temp_file in temp_files:
                temp_file.unlink()

    def test_git_diff_performance_many_files(self):
        """Test git diff performance with many changed files"""
        detector = VersionDetector()

        # Mock getting many changed files
        fake_files = [Path(f"file_{i}.tf") for i in range(100)]

        with patch.object(detector, "get_changed_files", return_value=fake_files):
            with patch.object(detector, "find_matching_parser", return_value=None):
                start_time = time.time()
                issues = detector.detect_issues()
                processing_time = time.time() - start_time

                # Should handle 100 files quickly even if no parser matches
                assert processing_time < 2.0
                assert issues == []

    def test_parser_version_extraction_performance(self):
        """Test version extraction performance"""
        parser = TerraformParser()

        # Test performance with many version constraints
        test_constraints = [
            f"~> {i}.{j}.{k}" for i in range(10) for j in range(10) for k in range(10)
        ]

        start_time = time.time()
        for constraint in test_constraints:
            parser.extract_version(constraint)
        processing_time = time.time() - start_time

        # Should extract 1000 versions quickly (< 1 second)
        assert processing_time < 1.0

    def test_version_bound_checking_performance(self):
        """Test version bound checking performance"""
        parser = TerraformParser()

        # Test various constraint patterns
        test_constraints = []
        for i in range(1000):
            test_constraints.extend(
                [f"~> {i % 10}.0.0", f">= {i % 10}.0.0", f"= {i % 10}.0.0", f"> {i % 10}.0.0", "*"]
            )

        start_time = time.time()
        for constraint in test_constraints:
            parser.is_version_bound(constraint)
        processing_time = time.time() - start_time

        # Should check 5000 constraints quickly (< 1 second)
        assert processing_time < 1.0


class TestStressConditions:
    """Test BVD under stress conditions"""

    def test_deeply_nested_terraform_structure(self):
        """Test with deeply nested Terraform structure"""
        detector = VersionDetector()

        # Create a complex nested structure
        terraform_content = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "*"
    }
  }
}

terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0.0"
    }
  }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            issues = detector.detect_issues([temp_path])

            # Should handle multiple terraform blocks correctly
            assert len(issues) == 2  # aws and kubernetes unbound

            package_names = [issue.change.package_name for issue in issues]
            assert "hashicorp/aws" in package_names
            assert "hashicorp/kubernetes" in package_names

        finally:
            temp_path.unlink()

    def test_malformed_content_resilience(self):
        """Test resilience against various malformed content"""
        detector = VersionDetector()

        malformed_contents = [
            # Missing closing braces
            """terraform { required_providers { aws = { source = "hashicorp/aws" """,
            # Invalid JSON-like syntax
            """terraform = { "required_providers": { "aws": { source: hashicorp/aws } } }""",
            # Mixed valid/invalid
            """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0.0"
    }
    broken = {
      source = "broken/provider"
      # missing closing brace
    aws2 = {
      source = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }
}
""",
            # Empty content
            "",
            # Non-Terraform content
            "This is not Terraform configuration at all!",
            # Binary-like content
            "\x00\x01\x02\x03\x04\x05",
        ]

        for i, content in enumerate(malformed_contents):
            with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{i}.tf", delete=False) as f:
                f.write(content)
                temp_path = Path(f.name)

            try:
                # Should not crash, should handle gracefully
                issues = detector.detect_issues([temp_path])
                # May return empty list or partial results, but shouldn't crash
                assert isinstance(issues, list)

            finally:
                temp_path.unlink()

    def test_very_long_lines(self):
        """Test handling of very long lines"""
        detector = VersionDetector()

        # Create a Terraform file with very long lines
        long_source = "a" * 1000
        long_version = "1." + "0" * 500 + ".0"

        terraform_content = f"""
terraform {{
  required_providers {{
    very_long_provider = {{
      source  = "example/{long_source}"
      version = "~> {long_version}"
    }}
  }}
}}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tf", delete=False) as f:
            f.write(terraform_content)
            temp_path = Path(f.name)

        try:
            # Should handle very long lines without issues
            issues = detector.detect_issues([temp_path])

            # Should still detect the provider properly
            assert len(issues) == 0  # Properly bound with ~>

        finally:
            temp_path.unlink()

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters"""
        detector = VersionDetector()

        terraform_content = """
# Terraform with unicode: éñüñü 中文 🎉
terraform {
  required_providers {
    unicode_provider = {
      source  = "example/provider-with-unicode-chars"
      version = ">= 1.0.0"  # Comment with unicode: ñññ
    }

    /* Multi-line comment with special chars: ©®™ */
    special_chars = {
      source  = "example/special-chars-symbols"
      version = "*"
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
            issues = detector.detect_issues([temp_path])

            # Should handle unicode properly and find 2 unbound issues
            assert len(issues) == 2

            package_names = [issue.change.package_name for issue in issues]
            assert any("unicode" in name for name in package_names)
            assert any("special" in name for name in package_names)

        finally:
            temp_path.unlink()


class TestMemoryUsage:
    """Test memory usage characteristics"""

    def test_memory_usage_large_files(self):
        """Test that memory usage stays reasonable with large files"""
        try:
            import os

            import psutil
        except ImportError:
            pytest.skip("psutil not available for memory testing")

        detector = VersionDetector()

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create multiple large files
        temp_files = []
        for file_idx in range(10):
            terraform_content = "terraform {\n  required_providers {\n"

            # 100 providers per file
            for i in range(100):
                terraform_content += f"""
    provider_{file_idx}_{i:03d} = {{
      source  = "example/provider_{file_idx}_{i:03d}"
      version = ">= {i % 10}.0.0"
    }}
"""
            terraform_content += "  }\n}\n"

            with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{file_idx}.tf", delete=False) as f:
                f.write(terraform_content)
                temp_files.append(Path(f.name))

        try:
            # Process all files
            issues = detector.detect_issues(temp_files)

            # Check memory usage after processing
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory

            # Memory increase should be reasonable (< 100MB for this test)
            assert memory_increase < 100, f"Memory increased by {memory_increase:.1f}MB"

            # Should find 1000 issues (100 per file * 10 files)
            assert len(issues) == 1000

        finally:
            for temp_file in temp_files:
                temp_file.unlink()


