"""
Parsers for different dependency file formats
"""

from .base import DependencyParser
from .terraform import TerraformParser

__all__ = ["DependencyParser", "TerraformParser"]