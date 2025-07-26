"""
Terraform provider dependency parser
"""

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, List

import hcl2

# Avoid circular import issues
if TYPE_CHECKING:
    from ..core import VersionChange


from .base import DependencyParser


class TerraformParser(DependencyParser):
    """Parser for Terraform provider dependencies"""

    @property
    def supported_files(self) -> List[str]:
        return ["*.tf", "versions.tf", "main.tf", "providers.tf"]

    @property
    def name(self) -> str:
        return "Terraform"

    def parse_dependencies(self, file_path: Path, content: str) -> List["VersionChange"]:
        """Parse Terraform provider dependencies"""
        from ..core import VersionChange

        changes = []

        if hcl2 is None:
            print("Warning: python-hcl2 not installed, skipping HCL parsing", file=sys.stderr)
            return changes

        try:
            # Parse HCL content
            parsed = hcl2.loads(content)

            # Extract provider requirements
            terraform_blocks = parsed.get("terraform", [])
            for tf_block in terraform_blocks:
                if isinstance(tf_block, dict) and "required_providers" in tf_block:
                    providers = tf_block["required_providers"]
                    if isinstance(providers, list):
                        providers = providers[0]

                    for provider_name, provider_config in providers.items():
                        if isinstance(provider_config, dict) and "version" in provider_config:
                            version_constraint = provider_config["version"]
                            source = provider_config.get("source", provider_name)

                            changes.append(
                                VersionChange(
                                    package_name=source,
                                    old_version=None,  # Will be populated by diff logic
                                    new_version=self.extract_version(version_constraint)
                                    or version_constraint,
                                    old_constraint=None,
                                    new_constraint=version_constraint,
                                    file_path=str(file_path),
                                )
                            )

        except Exception as e:
            print(f"Error parsing {file_path}: {e}", file=sys.stderr)

        return changes

    def is_version_bound(self, constraint: str) -> bool:
        """Check if Terraform version constraint properly bounds major version"""
        # Unbound patterns
        unbound_patterns = [
            r"^\s*>=\s*\d+\.\d+",  # >= without upper bound
            r"^\s*>\s*\d+\.\d+",  # > without upper bound
            r"^\s*\*\s*$",  # Just *
        ]

        for pattern in unbound_patterns:
            if re.match(pattern, constraint.strip()):
                return False

        # Properly bound patterns
        bound_patterns = [
            r"^\s*~>\s*\d+\.\d+",  # ~> pessimistic operator
            r"^\s*=\s*\d+\.\d+\.\d+",  # Exact version
            r'^\s*"\s*\d+\.\d+\.\d+\s*"',  # Quoted exact version
            r"^\s*\d+\.\d+\.\d+\s*$",  # Plain exact version without operator
        ]

        for pattern in bound_patterns:
            if re.match(pattern, constraint.strip()):
                return True

        return False
