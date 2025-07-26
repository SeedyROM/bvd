
"""
Breaking Version Detector (BVD)
Extensible tool for detecting breaking dependency version changes
"""

from .core import (
    Severity,
    IssueType, 
    VersionChange,
    Issue,
    DependencyParser,
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