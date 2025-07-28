"""
Tests for semver utility functions
"""

from src.bvd.semver import (
    compare_versions,
    extract_version_from_constraint,
    is_valid_semver,
    normalize_version,
)


class TestSemverUtils:
    """Test semantic version utility functions"""

    def test_extract_version_from_constraint(self):
        """Test version extraction from various constraint formats"""
        test_cases = [
            # Standard semver
            ("~> 1.2.3", "1.2.3"),
            ("= 2.0.0", "2.0.0"),
            (">= 1.0.0", "1.0.0"),
            ("1.5.2", "1.5.2"),
            # Incomplete versions
            ("~> 1.2", "1.2"),
            ("= 2.0", "2.0"),
            ("1.5", "1.5"),
            # Major-only versions
            ("~> 1", "1"),
            ("= 2", "2"),
            ("5", "5"),
            # Pre-release versions
            ("1.0.0-alpha.1", "1.0.0-alpha.1"),
            ("~> 2.1.0-beta", "2.1.0-beta"),
            # Complex constraints
            (">= 1.0.0, < 2.0.0", "1.0.0"),
            ("^1.2.3", "1.2.3"),
            # Invalid cases
            ("~> A.B.C", None),
            ("~> #.@.!", None),
            ("latest", None),
            ("", None),
            ("invalid", None),
        ]

        for constraint, expected in test_cases:
            result = extract_version_from_constraint(constraint)
            assert result == expected, (
                f"Failed for constraint '{constraint}': expected {expected}, got {result}"
            )

    def test_is_valid_semver(self):
        """Test semver validation"""
        valid_cases = [
            "1.2.3",
            "1.2",
            "1",
            "1.0.0-alpha.1",
            "2.1.0-beta",
            "10.20.30",
        ]

        invalid_cases = [
            "A.B.C",
            "#.@.!",
            "latest",
            "",
            "not.a.version",
        ]

        for version_str in valid_cases:
            assert is_valid_semver(version_str), f"Expected '{version_str}' to be valid"

        for version_str in invalid_cases:
            assert not is_valid_semver(version_str), f"Expected '{version_str}' to be invalid"

    def test_normalize_version(self):
        """Test version normalization"""
        test_cases = [
            ("1.2.3", "1.2.3"),
            ("1.2", "1.2"),  # packaging doesn't auto-pad incomplete versions
            ("1", "1"),  # packaging doesn't auto-pad incomplete versions
            ("1.0.0-alpha.1", "1.0.0a1"),  # packaging normalizes pre-release
            ("2.1.0-beta", "2.1.0b0"),
        ]

        invalid_cases = [
            "A.B.C",
            "#.@.!",
            "latest",
            "",
        ]

        for version_str, expected in test_cases:
            result = normalize_version(version_str)
            assert result == expected, (
                f"Failed for version '{version_str}': expected {expected}, got {result}"
            )

        for version_str in invalid_cases:
            result = normalize_version(version_str)
            assert result is None, (
                f"Expected None for invalid version '{version_str}', got {result}"
            )

    def test_compare_versions(self):
        """Test version comparison"""
        test_cases = [
            # Major version changes (upgrades)
            ("1.0.0", "2.0.0", (1, 0, 0)),
            ("1.2.3", "3.0.0", (2, -2, -3)),
            # Major version changes (downgrades)
            ("2.0.0", "1.0.0", (-1, 0, 0)),
            ("3.0.0", "1.2.3", (-2, 2, 3)),
            # Minor version changes (upgrades)
            ("1.0.0", "1.1.0", (0, 1, 0)),
            ("1.2.3", "1.5.0", (0, 3, -3)),
            # Minor version changes (downgrades)
            ("1.5.0", "1.2.0", (0, -3, 0)),
            ("1.5.3", "1.2.1", (0, -3, -2)),
            # Patch version changes (upgrades)
            ("1.0.0", "1.0.1", (0, 0, 1)),
            ("1.2.3", "1.2.5", (0, 0, 2)),
            # Patch version changes (downgrades)
            ("1.0.5", "1.0.1", (0, 0, -4)),
            ("1.2.5", "1.2.3", (0, 0, -2)),
            # No change
            ("1.2.3", "1.2.3", (0, 0, 0)),
            # Incomplete versions
            ("1.2", "1.3", (0, 1, 0)),
            ("1", "2", (1, 0, 0)),
            ("1.3", "1.2", (0, -1, 0)),
            ("2", "1", (-1, 0, 0)),
            # Mixed formats
            ("1.2", "1.2.1", (0, 0, 1)),
            ("1", "1.0.1", (0, 0, 1)),
            ("1.2.1", "1.2", (0, 0, -1)),
            ("1.0.1", "1", (0, 0, -1)),
        ]

        for old_ver, new_ver, expected in test_cases:
            result = compare_versions(old_ver, new_ver)
            assert result == expected, (
                f"Failed for {old_ver} -> {new_ver}: expected {expected}, got {result}"
            )

        # Invalid version cases
        invalid_cases = [
            ("invalid", "1.2.3"),
            ("1.2.3", "invalid"),
            ("A.B.C", "1.2.3"),
        ]

        for old_ver, new_ver in invalid_cases:
            result = compare_versions(old_ver, new_ver)
            assert result is None, (
                f"Expected None for invalid versions {old_ver} -> {new_ver}, got {result}"
            )

    def test_integration_with_packaging_library(self):
        """Test that our utilities work correctly with packaging library behavior"""
        # Test that incomplete versions are properly handled
        from packaging import version

        # These should all be valid and normalize correctly
        test_versions = ["1", "1.2", "1.2.3"]

        for ver_str in test_versions:
            # Should be extractable
            extracted = extract_version_from_constraint(f"~> {ver_str}")
            assert extracted == ver_str

            # Should be valid
            assert is_valid_semver(ver_str)

            # Should normalize
            normalized = normalize_version(ver_str)
            assert normalized is not None

            # Should be parseable by packaging
            parsed = version.parse(ver_str)
            assert parsed is not None
