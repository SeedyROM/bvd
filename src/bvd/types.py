"""
Data types and enums for the Breaking Version Detector
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def to_emoji(self) -> str:
        return {
            Severity.INFO: "ℹ️",
            Severity.WARNING: "⚠️",
            Severity.ERROR: "❌",
            Severity.CRITICAL: "🚨",
        }[self]


class IssueType(Enum):
    MAJOR_VERSION_BUMP = "major_version_bump"
    MINOR_VERSION_BUMP = "minor_version_bump"
    PATCH_VERSION_BUMP = "patch_version_bump"
    UNBOUND_VERSION = "unbound_version"
    LOOSE_CONSTRAINT = "loose_constraint"


@dataclass
class VersionChange:
    package_name: str
    old_version: Optional[str]
    new_version: str
    old_constraint: Optional[str]
    new_constraint: str
    file_path: str
    line_number: Optional[int] = None


@dataclass
class Issue:
    severity: Severity
    issue_type: IssueType
    message: str
    change: VersionChange
    suggestion: Optional[str] = None
