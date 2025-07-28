"""
Semantic version utilities for dependency parsers
"""

import re
from typing import Optional

from packaging import version


def extract_version_from_constraint(constraint: str) -> Optional[str]:
    """
    Extract actual version from constraint string.

    Supports:
    - Full semver: 1.2.3
    - Incomplete versions: 1.2, 1
    - Pre-release versions: 1.2.3-alpha.1
    - Various constraint operators: ~>, =, >=, etc.

    Args:
        constraint: Version constraint string like "~> 1.2.3" or "= 1.2"

    Returns:
        Extracted version string or None if no valid version found
    """
    # Support full semver (1.2.3), incomplete versions (1.2), and major-only (1)
    semver_pattern = r"(\d+(?:\.\d+)?(?:\.\d+)?(?:-[a-zA-Z0-9\-\.]+)?)"
    match = re.search(semver_pattern, constraint)
    return match.group(1) if match else None


def is_valid_semver(version_str: str) -> bool:
    """
    Check if a version string is valid semver using packaging library.

    Args:
        version_str: Version string to validate

    Returns:
        True if valid semver, False otherwise
    """
    try:
        version.parse(version_str)
        return True
    except version.InvalidVersion:
        return False


def normalize_version(version_str: str) -> Optional[str]:
    """
    Normalize a version string using packaging library.

    Examples:
    - "1.2" -> "1.2.0"
    - "1" -> "1.0.0"
    - "1.2.3-alpha" -> "1.2.3a0"

    Args:
        version_str: Version string to normalize

    Returns:
        Normalized version string or None if invalid
    """
    try:
        parsed = version.parse(version_str)
        return str(parsed)
    except version.InvalidVersion:
        return None


def compare_versions(old_ver: str, new_ver: str) -> Optional[tuple[int, int, int]]:
    """
    Compare two versions and return the change in (major, minor, patch).

    Args:
        old_ver: Old version string
        new_ver: New version string

    Returns:
        Tuple of (major_diff, minor_diff, patch_diff) or None if versions are invalid
    """
    try:
        old_v = version.parse(old_ver)
        new_v = version.parse(new_ver)

        major_diff = new_v.major - old_v.major
        minor_diff = new_v.minor - old_v.minor
        patch_diff = new_v.micro - old_v.micro

        return (major_diff, minor_diff, patch_diff)
    except version.InvalidVersion:
        return None
