"""
Core classes for the Breaking Version Detector
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parsers.base import DependencyParser
from .parsers.terraform import TerraformParser
from .semver import compare_versions
from .types import Issue, IssueType, Severity, VersionChange


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
                IssueType.MAJOR_VERSION_DOWNGRADE: Severity.CRITICAL,
                IssueType.MINOR_VERSION_DOWNGRADE: Severity.WARNING,
                IssueType.PATCH_VERSION_DOWNGRADE: Severity.WARNING,
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
        version_diff = compare_versions(old_ver, new_ver)
        if version_diff is None:
            # Handle non-semver versions
            return None

        major_diff, minor_diff, patch_diff = version_diff

        # Check for major changes first (upgrades and downgrades)
        if major_diff > 0:
            return IssueType.MAJOR_VERSION_BUMP
        elif major_diff < 0:
            return IssueType.MAJOR_VERSION_DOWNGRADE
        # Then minor changes
        elif minor_diff > 0:
            return IssueType.MINOR_VERSION_BUMP
        elif minor_diff < 0:
            return IssueType.MINOR_VERSION_DOWNGRADE
        # Finally patch changes
        elif patch_diff > 0:
            return IssueType.PATCH_VERSION_BUMP
        elif patch_diff < 0:
            return IssueType.PATCH_VERSION_DOWNGRADE

        return None

    def detect_issues(
        self, file_paths: Optional[List[Path]] = None, base_ref: str = "HEAD~1"
    ) -> List[Issue]:
        """Main detection method"""
        if file_paths is None:
            file_paths = self.get_changed_files(base_ref)

        issues = []
        for file_path in file_paths:
            issues.extend(self._process_file_for_issues(file_path, base_ref))

        return issues

    def _process_file_for_issues(self, file_path: Path, base_ref: str) -> List[Issue]:
        """Process a single file and return any issues found"""
        parser = self.find_matching_parser(file_path)
        if not parser:
            return []

        try:
            changes = self.get_dependency_changes(file_path, base_ref)
            issues = []

            for change in changes:
                if self._should_ignore_package(change.package_name):
                    continue

                issues.extend(self._process_dependency_change(change, parser))

            return issues

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)
            return []

    def _process_dependency_change(
        self, change: VersionChange, parser: DependencyParser
    ) -> List[Issue]:
        """Process a single dependency change and return any issues found"""
        issues = []

        # Check for unbound versions
        if not parser.is_version_bound(change.new_constraint):
            issue = self._create_unbound_version_issue(change)
            if issue:
                issues.append(issue)

        # Check for version changes
        if change.old_version and change.old_version != change.new_version:
            issue = self._create_version_change_issue(change)
            if issue:
                issues.append(issue)

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

    def _should_ignore_package(self, package_name: str) -> bool:
        """Check if a package should be ignored based on configuration"""
        ignore_packages = self.config.get("ignore_packages") or []
        return package_name in ignore_packages

    def _resolve_severity(self, base_severity: Severity, package_name: str) -> Severity:
        """Resolve final severity, considering critical package overrides"""
        critical_packages = self.config.get("critical_packages") or {}
        if package_name in critical_packages:
            return critical_packages[package_name]
        return base_severity

    def _create_unbound_version_issue(self, change: VersionChange) -> Optional[Issue]:
        """Create an issue for unbound version constraints"""
        base_severity = self.config["rules"][IssueType.UNBOUND_VERSION]
        severity = self._resolve_severity(base_severity, change.package_name)
        suggestion = self._get_unbound_constraint_suggestion(change)
        message = f"Unbound version constraint '{change.new_constraint}' for {change.package_name}"

        return Issue(
            severity=severity,
            issue_type=IssueType.UNBOUND_VERSION,
            message=message,
            change=change,
            suggestion=suggestion,
        )

    def _create_version_change_issue(self, change: VersionChange) -> Optional[Issue]:
        """Create an issue for version changes"""
        # This method should only be called when old_version is not None
        assert change.old_version is not None, "old_version should not be None"
        issue_type = self.analyze_version_change(change.old_version, change.new_version)
        if not issue_type:  # pragma: no cover
            return None

        base_severity = self.config["rules"][issue_type]
        severity = self._resolve_severity(base_severity, change.package_name)

        # Generate explicit messages based on issue type
        if "downgrade" in issue_type.value:
            if issue_type == IssueType.MAJOR_VERSION_DOWNGRADE:
                message = (
                    f"Major version downgrade detected: {change.package_name} "
                    f"downgraded from {change.old_version} to {change.new_version} - "
                    f"potential feature loss and security vulnerabilities"
                )
                suggestion = (
                    f"Review {change.package_name} changelog for removed features and fixes. "
                    f"Verify your code doesn't depend on features from {change.old_version}. "
                    "Consider security implications of missing patches."
                )
            elif issue_type == IssueType.MINOR_VERSION_DOWNGRADE:
                message = (
                    f"Minor version downgrade detected: {change.package_name} "
                    f"downgraded from {change.old_version} to {change.new_version} - "
                    f"potential feature loss and missing bug fixes"
                )
                suggestion = (
                    f"Review {change.package_name} changelog for removed features and bug fixes. "
                    f"Verify your code doesn't depend on features from {change.old_version}."
                )
            else:  # PATCH_VERSION_DOWNGRADE
                message = (
                    f"Patch version downgrade detected: {change.package_name} "
                    f"downgraded from {change.old_version} to {change.new_version} - "
                    f"missing bug fixes and security patches"
                )
                suggestion = (
                    f"Review {change.package_name} changelog for bug fixes and security patches "
                    f"that may be missing in version {change.new_version}."
                )
        else:
            # Original upgrade messages
            message = (
                f"{issue_type.value.replace('_', ' ').title()} detected: "
                f"{change.package_name} changed from {change.old_version} to {change.new_version}"
            )
            suggestion = (
                f"Review breaking changes in {change.package_name} changelog "
                f"between versions {change.old_version} and {change.new_version}"
            )

        return Issue(
            severity=severity,
            issue_type=issue_type,
            message=message,
            change=change,
            suggestion=suggestion,
        )

    def _get_unbound_constraint_suggestion(self, change: VersionChange) -> str:
        """Generate suggestion for unbound version constraints"""
        if change.new_constraint.strip() == "*":
            return (
                "Wildcard constraints are strictly forbidden. "
                "Use a specific version like '= 1.2.3' or a bounded constraint like '~> 1.2'"
            )
        else:
            return f"Consider using '~> {change.new_version}' to bound to major version"
