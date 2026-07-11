#!/data/data/com.termux/files/usr/bin/env python
"""
Convert Python 2 print statements to Python 3 print() functions using Ruff.
"""

import subprocess
import sys
import os
from pathlib import Path


def convert_print_statements(file_or_dir, preview=False, dry_run=False):
    """
    Convert Python 2 print statements to Python 3 style.

    Args:
        file_or_dir: Path to file or directory to convert
        preview: Use preview mode for more comprehensive conversion
        dry_run: Show what would be changed without making changes
    """
    target = str(file_or_dir)

    # Build the ruff command
    cmd = [
        "ruff",
        "check",
        "--fix",
        "--select",
        "UP010",  # pyupgrade rule for print conversion
        target,
    ]

    if preview:
        cmd.append("--preview")

    if dry_run:
        cmd.append("--diff")  # Show diff instead of applying changes
        print(f"🔍 DRY RUN - Showing changes for: {target}\n")
        print("=" * 60)

    try:
        # Run ruff
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        # Print output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            if dry_run:
                print("\n✅ Dry run complete. No changes were made.")
            else:
                print(f"\n✅ Successfully converted print statements in: {target}")
        else:
            print(f"\n⚠️  Ruff exited with code {result.returncode}")
            return False

        return True

    except FileNotFoundError:
        print("❌ Ruff not found. Please install it first:")
        print("   pip install ruff")
        print("   # or")
        print("   brew install ruff  # on macOS")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def convert_with_alternative_rules(file_or_dir, dry_run=False):
    """
    Use alternative Ruff rules (T201) for print conversion.
    """
    target = str(file_or_dir)

    cmd = [
        "ruff",
        "check",
        "--fix",
        "--select",
        "T201",  # print statement rule
        target,
    ]

    if dry_run:
        cmd.append("--diff")
        print(f"🔍 DRY RUN - Using T201 rule for: {target}\n")
        print("=" * 60)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print(f"\n✅ Conversion complete using T201 rule.")
            return True
        return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert Python 2 print statements to Python 3 using Ruff")
    parser.add_argument("path", help="File or directory to convert (e.g., script.py or ./src)")
    parser.add_argument("--preview", action="store_true", help="Use preview mode for more comprehensive conversion")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--alternative", action="store_true", help="Use alternative T201 rule instead of UP010")
    parser.add_argument(
        "--recursive", action="store_true", help="Process directories recursively (default: True for directories)"
    )

    args = parser.parse_args()

    # Check if path exists
    if not os.path.exists(args.path):
        print(f"❌ Path not found: {args.path}")
        sys.exit(1)

    # If it's a directory and recursive flag is set, process all Python files
    if os.path.isdir(args.path) and args.recursive:
        python_files = list(Path(args.path).rglob("*.py"))
        if not python_files:
            print(f"⚠️  No Python files found in: {args.path}")
            sys.exit(0)

        print(f"📁 Found {len(python_files)} Python files in {args.path}\n")

        success_count = 0
        for py_file in python_files:
            print(f"\n{'=' * 60}")
            print(f"Processing: {py_file}")

            if args.alternative:
                success = convert_with_alternative_rules(py_file, args.dry_run)
            else:
                success = convert_print_statements(py_file, args.preview, args.dry_run)

            if success:
                success_count += 1

        print(f"\n{'=' * 60}")
        print(f"✅ Processed {success_count}/{len(python_files)} files successfully")

    else:
        # Process single file
        if args.alternative:
            convert_with_alternative_rules(args.path, args.dry_run)
        else:
            convert_print_statements(args.path, args.preview, args.dry_run)


if __name__ == "__main__":
    main()
