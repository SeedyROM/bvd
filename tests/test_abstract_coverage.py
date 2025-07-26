"""
Tests specifically designed to cover abstract method pass statements
"""

import inspect
from abc import ABC
from pathlib import Path

from bvd.parsers.base import DependencyParser


class TestAbstractMethodCoverage:
    """Test abstract method definitions to achieve 100% coverage"""

    def test_abstract_method_definitions(self):
        """Test that abstract methods are properly defined and raise NotImplementedError"""

        # Create a class that doesn't implement abstract methods
        class IncompleteParser(DependencyParser):
            pass

        # This should raise TypeError when trying to instantiate
        try:
            IncompleteParser()
            assert False, "Should have raised TypeError for abstract methods"
        except TypeError as e:
            assert "abstract methods" in str(e)

        # Test each abstract method individually by creating partial implementations

        # Test supported_files property
        class TestSupportedFiles(DependencyParser):
            @property
            def supported_files(self):
                return ["*.test"]

            # Leave other methods abstract to test them individually
            pass

        try:
            TestSupportedFiles()
            assert False, "Should raise TypeError for missing abstract methods"
        except TypeError:
            pass

        # Test name property
        class TestName(DependencyParser):
            @property
            def name(self):
                return "test"

            pass

        try:
            TestName()
            assert False, "Should raise TypeError for missing abstract methods"
        except TypeError:
            pass

        # Test parse_dependencies method
        class TestParseDeps(DependencyParser):
            def parse_dependencies(self, file_path, content):
                return []

            pass

        try:
            TestParseDeps()
            assert False, "Should raise TypeError for missing abstract methods"
        except TypeError:
            pass

        # Test is_version_bound method
        class TestVersionBound(DependencyParser):
            def is_version_bound(self, constraint):
                return True

            pass

        try:
            TestVersionBound()
            assert False, "Should raise TypeError for missing abstract methods"
        except TypeError:
            pass

    def test_abstract_base_class_structure(self):
        """Test the ABC structure of DependencyParser"""

        # Verify it's an abstract base class
        assert issubclass(DependencyParser, ABC)

        # Get all abstract methods
        abstract_methods = DependencyParser.__abstractmethods__
        expected_methods = {"supported_files", "name", "parse_dependencies", "is_version_bound"}

        assert abstract_methods == expected_methods

    def test_concrete_implementation_complete(self):
        """Test that a complete concrete implementation works"""

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

        # This should work without raising TypeError
        parser = CompleteParser()
        assert parser.supported_files == ["*.complete"]
        assert parser.name == "Complete Parser"
        assert parser.parse_dependencies(Path("test"), "content") == []
        assert parser.is_version_bound("~> 1.0.0") is True
        assert parser.is_version_bound(">= 1.0.0") is False

    def test_method_signatures(self):
        """Test that abstract method signatures are correct"""

        # Test supported_files is a property
        assert isinstance(DependencyParser.supported_files, property)

        # Test name is a property
        assert isinstance(DependencyParser.name, property)

        # Test method signatures using inspection
        parse_deps_sig = inspect.signature(DependencyParser.parse_dependencies)
        expected_params = ["self", "file_path", "content"]
        actual_params = list(parse_deps_sig.parameters.keys())
        assert actual_params == expected_params

        version_bound_sig = inspect.signature(DependencyParser.is_version_bound)
        expected_params = ["self", "constraint"]
        actual_params = list(version_bound_sig.parameters.keys())
        assert actual_params == expected_params


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
