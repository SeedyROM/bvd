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
        self.config = config or self._default_config()
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
            }
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
            result = subprocess.run([
                "git", "diff", "--name-only", base_ref
            ], capture_output=True, text=True, check=True)
            
            changed_files = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    path = Path(line)
                    if path.exists():
                        changed_files.append(path)
            
            return changed_files
            
        except subprocess.CalledProcessError as e:
            print(f"Error getting changed files: {e}", file=sys.stderr)
            return []
    
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
    
    def detect_issues(self, file_paths: Optional[List[Path]] = None) -> List[Issue]:
        """Main detection method"""
        if file_paths is None:
            file_paths = self.get_changed_files()
        
        issues = []
        
        for file_path in file_paths:
            parser = self.find_matching_parser(file_path)
            if not parser:
                continue
                
            try:
                content = file_path.read_text()
                changes = parser.parse_dependencies(file_path, content)
                
                for change in changes:
                    # Check for unbound versions
                    if not parser.is_version_bound(change.new_constraint):
                        issues.append(Issue(
                            severity=self.config["rules"][IssueType.UNBOUND_VERSION],
                            issue_type=IssueType.UNBOUND_VERSION,
                            message=f"Unbound version constraint '{change.new_constraint}' for {change.package_name}",
                            change=change,
                            suggestion=f"Consider using '~> {change.new_version}' to bound to major version"
                        ))
                    
                    # TODO: Add version change detection logic
                    # This would require getting the old version from git diff
                    
            except Exception as e:
                print(f"Error processing {file_path}: {e}", file=sys.stderr)
        
        return issues
    
    def report_issues(self, issues: List[Issue], format: str = "text") -> str:
        """Generate report of issues"""
        if format == "json":
            return json.dumps([
                {
                    "severity": issue.severity.value,
                    "type": issue.issue_type.value,
                    "message": issue.message,
                    "file": issue.change.file_path,
                    "package": issue.change.package_name,
                    "suggestion": issue.suggestion
                }
                for issue in issues
            ], indent=2)
        
        # Text format
        report = []
        for issue in issues:
            icon = {
                Severity.INFO: "ℹ️",
                Severity.WARNING: "⚠️", 
                Severity.ERROR: "❌",
                Severity.CRITICAL: "🚨"
            }[issue.severity]
            
            report.append(f"{icon} {issue.severity.value.upper()}: {issue.message}")
            report.append(f"   File: {issue.change.file_path}")
            report.append(f"   Package: {issue.change.package_name}")
            if issue.suggestion:
                report.append(f"   Suggestion: {issue.suggestion}")
            report.append("")
        
        return "\n".join(report)