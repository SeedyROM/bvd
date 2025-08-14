"""
Invoke tasks for BVD (Breaking Version Detector) development commands.

This file replaces the Makefile and provides the same functionality using invoke.
Run `invoke --list` to see all available tasks.
"""

from invoke import task


@task
def format(c):
    """Format code with ruff."""
    c.run("uv run ruff format src/ tests/")


@task
def lint(c):
    """Check code style and quality with ruff."""
    c.run("uv run ruff check src/ tests/")


@task(name="lint-fix")
def lint_fix(c):
    """Fix code style issues automatically."""
    c.run("uv run ruff check --fix src/ tests/")


@task
def test(c, cov=False, xml=False):
    """Run all tests with pytest.

    Args:
        cov: Run with coverage report (--cov)
        xml: Run with XML coverage report for CI (--xml)
    """
    cmd = "uv run pytest"

    if xml:
        cmd += " --cov=bvd --cov-report=xml"
    elif cov:
        cmd += " --cov=bvd --cov-report=term-missing --cov-report=html"

    cmd += " tests/"
    c.run(cmd)


@task
def build(c):
    """Build the package."""
    c.run("uv build")
