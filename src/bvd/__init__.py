"""
Breaking Version Detector (BVD)
Extensible tool for detecting breaking dependency version changes
"""

from .core import (
    DependencyParser,
    Issue,
    IssueType,
    Severity,
    VersionChange,
    VersionDetector,
)

__version__ = "0.1.0"
__all__ = [
    "Severity",
    "IssueType",
    "VersionChange",
    "Issue",
    "DependencyParser",
    "VersionDetector",
]
