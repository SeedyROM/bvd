"""
Command line interface for BVD
"""

import sys
from pathlib import Path

import click

from .core import VersionDetector, Severity


@click.command()
@click.option("--files", multiple=True, help="Specific files to check")
@click.option("--format", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("--base-ref", default="HEAD~1", help="Git ref to compare against")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(files, format, base_ref, verbose):
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
    
    try:
        issues = detector.detect_issues(file_paths)
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
                click.echo(f"\n❌ Found {len([i for i in issues if i.severity in [Severity.ERROR, Severity.CRITICAL]])} critical/error issues")
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
def check_file(file_path):
    """Check a specific file for unbound version constraints"""
    detector = VersionDetector()
    issues = detector.detect_issues([Path(file_path)])
    
    if issues:
        report = detector.report_issues(issues)
        click.echo(report)
        sys.exit(1)
    else:
        click.echo("✅ No issues found!")


if __name__ == "__main__":
    main()