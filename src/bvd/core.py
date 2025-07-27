"""
Core classes for the Breaking Version Detector
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from packaging import version

from .parsers.base import DependencyParser
from .parsers.terraform import TerraformParser


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


class VersionDetector:
    """Main detector class that orchestrates parsing and analysis"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        default_config = self._default_config()
        if config:
            # Merge user config with defaults
            self.config = default_config.copy()
            for key, value in config.items():
                if key == "rules" and isinstance(value, dict):
                    self.config["rules"].update(value)
                else:
                    self.config[key] = value
        else:
            self.config = default_config
        self.parsers: Dict[str, DependencyParser] = {}
        self._register_default_parsers()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "rules": {
                IssueType.MAJOR_VERSION_BUMP: Severity.CRITICAL,
                IssueType.MINOR_VERSION_BUMP: Severity.WARNING,
                IssueType.PATCH_VERSION_BUMP: Severity.INFO,
                IssueType.UNBOUND_VERSION: Severity.ERROR,
                IssueType.LOOSE_CONSTRAINT: Severity.WARNING,
            },
            "ignore_packages": [],
            "critical_packages": {
                "hashicorp/aws": Severity.CRITICAL,
                "hashicorp/kubernetes": Severity.CRITICAL,
            },
        }

    def _register_default_parsers(self):
        """Register built-in parsers"""
        self.register_parser(TerraformParser())

    def register_parser(self, parser: DependencyParser):
        """Register a new dependency parser"""
        self.parsers[parser.name] = parser

    def get_changed_files(self, base_ref: str = "HEAD~1") -> List[Path]:
        """Get list of changed files from git diff"""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref], capture_output=True, text=True, check=True
            )

            changed_files = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    path = Path(line)
                    if path.exists():
                        changed_files.append(path)

            return changed_files

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error getting changed files: {e}", file=sys.stderr)
            return []

    def get_file_content_at_ref(self, file_path: Path, ref: str) -> Optional[str]:
        """Get file content at a specific git ref"""
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{file_path}"], capture_output=True, text=True, check=True
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_dependency_changes(
        self, file_path: Path, base_ref: str = "HEAD~1"
    ) -> List[VersionChange]:
        """Get dependency changes between base_ref and current state"""
        parser = self.find_matching_parser(file_path)
        if not parser:
            return []

        changes = []

        try:
            # Get current content
            current_content = file_path.read_text()
            current_deps = parser.parse_dependencies(file_path, current_content)

            # Get old content from git
            old_content = self.get_file_content_at_ref(file_path, base_ref)
            if old_content is None:
                # File is new, treat all current deps as additions
                return current_deps

            old_deps = parser.parse_dependencies(file_path, old_content)

            # Create lookup maps
            old_dep_map = {dep.package_name: dep for dep in old_deps}
            current_dep_map = {dep.package_name: dep for dep in current_deps}

            # Find changes and additions
            for pkg_name, current_dep in current_dep_map.items():
                if pkg_name in old_dep_map:
                    old_dep = old_dep_map[pkg_name]
                    # Update with old version info
                    current_dep.old_version = old_dep.new_version
                    current_dep.old_constraint = old_dep.new_constraint

                changes.append(current_dep)

        except Exception as e:
            print(f"Error getting dependency changes for {file_path}: {e}", file=sys.stderr)

        return changes

    def find_matching_parser(self, file_path: Path) -> Optional[DependencyParser]:
        """Find parser that can handle the given file"""
        for parser in self.parsers.values():
            for pattern in parser.supported_files:
                if file_path.match(pattern) or file_path.name == pattern:
                    return parser
        return None

    def analyze_version_change(self, old_ver: str, new_ver: str) -> Optional[IssueType]:
        """Analyze version change and return issue type if any"""
        try:
            old_v = version.parse(old_ver)
            new_v = version.parse(new_ver)

            if new_v.major > old_v.major:
                return IssueType.MAJOR_VERSION_BUMP
            elif new_v.minor > old_v.minor:
                return IssueType.MINOR_VERSION_BUMP
            elif new_v.micro > old_v.micro:
                return IssueType.PATCH_VERSION_BUMP

        except version.InvalidVersion:
            # Handle non-semver versions
            pass

        return None

    def detect_issues(
        self, file_paths: Optional[List[Path]] = None, base_ref: str = "HEAD~1"
    ) -> List[Issue]:
        """Main detection method"""
        if file_paths is None:
            file_paths = self.get_changed_files(base_ref)

        issues = []

        for file_path in file_paths:
            parser = self.find_matching_parser(file_path)
            if not parser:
                continue

            try:
                # Get dependency changes with old/new version info
                changes = self.get_dependency_changes(file_path, base_ref)

                for change in changes:
                    # Skip ignored packages
                    ignore_packages = self.config.get("ignore_packages") or []
                    if change.package_name in ignore_packages:
                        continue

                    # Check for unbound versions
                    if not parser.is_version_bound(change.new_constraint):
                        severity = self.config["rules"][IssueType.UNBOUND_VERSION]
                        # Upgrade severity for critical packages
                        critical_packages = self.config.get("critical_packages") or {}
                        if change.package_name in critical_packages:
                            severity = critical_packages[change.package_name]

                        # Special handling for wildcard constraints
                        if change.new_constraint.strip() == "*":
                            suggestion = (
                                "Wildcard constraints are strictly forbidden. "
                                "Use a specific version like '= 1.2.3' or a bounded constraint "
                                "like '~> 1.2'"
                            )
                        else:
                            suggestion = (
                                f"Consider using '~> {change.new_version}' to bound to major "
                                "version"
                            )

                        issues.append(
                            Issue(
                                severity=severity,
                                issue_type=IssueType.UNBOUND_VERSION,
                                message=f"Unbound version constraint '{change.new_constraint}' "
                                f"for {change.package_name}",
                                change=change,
                                suggestion=suggestion,
                            )
                        )

                    # Check for version changes (if old version exists)
                    if change.old_version and change.old_version != change.new_version:
                        issue_type = self.analyze_version_change(
                            change.old_version, change.new_version
                        )
                        if issue_type:
                            severity = self.config["rules"][issue_type]
                            # Upgrade severity for critical packages
                            critical_packages = self.config.get("critical_packages") or {}
                            if change.package_name in critical_packages:
                                severity = critical_packages[change.package_name]

                            issues.append(
                                Issue(
                                    severity=severity,
                                    issue_type=issue_type,
                                    message=(
                                        f"{issue_type.value.replace('_', ' ').title()} detected: "
                                        f"{change.package_name} changed from {change.old_version} "
                                        f"to {change.new_version}"
                                    ),
                                    change=change,
                                    suggestion=(
                                        f"Review breaking changes in {change.package_name} "
                                        f"changelog between versions {change.old_version} and "
                                        f"{change.new_version}"
                                    ),
                                )
                            )

            except Exception as e:
                print(f"Error processing {file_path}: {e}", file=sys.stderr)

        return issues

    def report_issues(self, issues: List[Issue], format: str = "") -> str:
        """Generate report of issues"""
        if format == "json":
            return json.dumps(
                [
                    {
                        "severity": issue.severity.value,
                        "type": issue.issue_type.value,
                        "message": issue.message,
                        "file": issue.change.file_path,
                        "package": issue.change.package_name,
                        "suggestion": issue.suggestion,
                    }
                    for issue in issues
                ],
                indent=2,
            )

        # Text format
        report = []
        for issue in issues:
            report.append(
                f"{issue.severity.to_emoji()} {issue.severity.value.upper()}: {issue.message}"
            )
            report.append(f"   File: {issue.change.file_path}")
            report.append(f"   Package: {issue.change.package_name}")
            if issue.suggestion:
                report.append(f"   Suggestion: {issue.suggestion}")
            report.append("")

        return "\n".join(report)
