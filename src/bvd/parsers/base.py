"""
Abstract base classes for dependency parsers
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

# Avoid circular import issues
if TYPE_CHECKING:
    from ..core import VersionChange


class DependencyParser(ABC):
    """Abstract base class for dependency file parsers"""

    @property
    @abstractmethod
    def supported_files(self) -> List[str]:
        """Return list of file patterns this parser supports"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return human-readable name of this parser"""
        pass

    @abstractmethod
    def parse_dependencies(self, file_path: Path, content: str) -> List["VersionChange"]:
        """Parse dependencies from file content"""
        pass

    @abstractmethod
    def is_version_bound(self, constraint: str) -> bool:
        """Check if version constraint properly bounds major version"""
        pass

    def extract_version(self, constraint: str) -> Optional[str]:
        """Extract actual version from constraint string"""
        # Default implementation - override if needed
        semver_pattern = r"(\d+\.\d+\.\d+(?:-[a-zA-Z0-9\-\.]+)?)"
        match = re.search(semver_pattern, constraint)
        return match.group(1) if match else None
