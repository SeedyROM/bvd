"""
Command line interface for BVD
"""

import sys
from pathlib import Path

import click

from .core import Severity, VersionDetector


@click.command()
@click.option("--files", multiple=True, help="Specific files to check")
@click.option("--format", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("--base-ref", default="HEAD~1", help="Git ref to compare against")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def main(ctx, files, format, base_ref, verbose):
    """Breaking Version Detector - Find dangerous dependency changes"""

    if verbose:
        click.echo("🔍 Breaking Version Detector starting...")

    detector = VersionDetector()

    file_paths = None
    if files:
        file_paths = [Path(f) for f in files]
        if verbose:
            click.echo(f"Checking {len(file_paths)} specific files")
    else:
        if verbose:
            click.echo(f"Checking git changes since {base_ref}")
        # Get changed files to check if there's anything to process
        changed_files = detector.get_changed_files(base_ref)
        if not changed_files:
            # No files specified and no git changes - show help
            click.echo(ctx.get_help())
            sys.exit(0)

    try:
        issues = detector.detect_issues(file_paths, base_ref)
        report = detector.report_issues(issues, format)

        if report.strip():
            click.echo(report)
        else:
            if verbose:
                click.echo("✅ No issues found!")

        # Exit with error code if critical/error issues found
        has_errors = any(issue.severity in [Severity.ERROR, Severity.CRITICAL] for issue in issues)

        if has_errors:
            if verbose:
                critical_errors = [
                    i for i in issues if i.severity in [Severity.ERROR, Severity.CRITICAL]
                ]
                click.echo(f"\n❌ Found {len(critical_errors)} critical/error issues")
            sys.exit(1)
        elif issues:
            if verbose:
                click.echo(f"\n⚠️  Found {len(issues)} warnings")
            sys.exit(0)
        else:
            sys.exit(0)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--base-ref", default="HEAD~1", help="Git ref to compare against")
def check_file(file_path, base_ref):
    """Check a specific file for unbound version constraints"""
    detector = VersionDetector()
    issues = detector.detect_issues([Path(file_path)], base_ref)

    if issues:
        report = detector.report_issues(issues)
        click.echo(report)
        sys.exit(1)
    else:
        click.echo("✅ No issues found!")


if __name__ == "__main__":
    main()
