"""
Abstract base classes for dependency parsers
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from ..semver import extract_version_from_constraint
from ..types import VersionChange


class DependencyParser(ABC):  # pragma: no cover
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
        # Default implementation uses shared semver utility - override if needed
        return extract_version_from_constraint(constraint)
