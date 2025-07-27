"""
Tests for abstract base classes and their interface contracts.

This module focuses specifically on testing the abstract DependencyParser base class
to ensure proper interface definition and inheritance behavior.
"""

import inspect
from abc import ABC
from pathlib import Path

import pytest

from bvd.parsers.base import DependencyParser


class TestDependencyParserAbstractInterface:
    """Test the abstract interface definition of DependencyParser"""

    def test_is_abstract_base_class(self):
        """Test that DependencyParser is properly defined as an ABC"""
        assert issubclass(DependencyParser, ABC)

        # Verify all expected abstract methods are defined
        abstract_methods = DependencyParser.__abstractmethods__
        expected_methods = {"supported_files", "name", "parse_dependencies", "is_version_bound"}
        assert abstract_methods == expected_methods

    def test_cannot_instantiate_abstract_class(self):
        """Test that abstract base class cannot be instantiated"""
        with pytest.raises(TypeError, match="abstract methods"):
            DependencyParser()

    def test_abstract_method_signatures(self):
        """Test that abstract methods have correct signatures"""
        # Test properties
        assert isinstance(DependencyParser.supported_files, property)
        assert isinstance(DependencyParser.name, property)

        # Test method signatures
        parse_deps_sig = inspect.signature(DependencyParser.parse_dependencies)
        assert list(parse_deps_sig.parameters.keys()) == ["self", "file_path", "content"]

        version_bound_sig = inspect.signature(DependencyParser.is_version_bound)
        assert list(version_bound_sig.parameters.keys()) == ["self", "constraint"]

    def test_extract_version_concrete_method(self):
        """Test that extract_version is a concrete method with proper implementation"""

        # Create a minimal concrete implementation to test the inherited method
        class TestParser(DependencyParser):
            @property
            def supported_files(self):
                return ["*.test"]

            @property
            def name(self):
                return "Test Parser"

            def parse_dependencies(self, file_path, content):
                return []

            def is_version_bound(self, constraint):
                return True

        parser = TestParser()

        # Test extract_version method (inherited from base)
        assert parser.extract_version("~> 1.2.3") == "1.2.3"
        assert parser.extract_version(">= 2.0.0") == "2.0.0"
        assert parser.extract_version("= 1.0.0") == "1.0.0"


class TestAbstractMethodEnforcement:
    """Test that abstract methods are properly enforced during inheritance"""

    def test_incomplete_implementation_fails(self):
        """Test that partial implementations cannot be instantiated"""

        # Missing all abstract methods
        class EmptyParser(DependencyParser):
            pass

        with pytest.raises(TypeError):
            EmptyParser()

        # Missing some abstract methods
        class PartialParser(DependencyParser):
            @property
            def supported_files(self):
                return ["*.partial"]

        with pytest.raises(TypeError):
            PartialParser()

    def test_complete_implementation_succeeds(self):
        """Test that complete implementations work correctly"""

        class CompleteParser(DependencyParser):
            @property
            def supported_files(self):
                return ["*.complete"]

            @property
            def name(self):
                return "Complete Parser"

            def parse_dependencies(self, file_path, content):
                return []

            def is_version_bound(self, constraint):
                return constraint.startswith("~>")

        # Should instantiate successfully
        parser = CompleteParser()

        # Test all interface methods work
        assert parser.supported_files == ["*.complete"]
        assert parser.name == "Complete Parser"
        assert parser.parse_dependencies(Path("test.complete"), "content") == []
        assert parser.is_version_bound("~> 1.0.0") is True
        assert parser.is_version_bound(">= 1.0.0") is False
        assert parser.extract_version("~> 2.1.0") == "2.1.0"
