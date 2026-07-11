#!/data/data/com.termux/files/usr/bin/env python

import shutil
import sys
from pathlib import Path

EMPTY_MODE = "-e" in sys.argv
REMOVE_MODE = "-r" in sys.argv
SKIP_DIRS = {"lazy", ".git", "var"}

# Define junk files once
JUNK_FILES = {
    "license",
    "license.rst",
    "license.md",
    "license.txt",
    "license.mit",
    "author",
    "authors",
    "authors.md",
    "copying",
    "contributing",
    ".travis.yml",
    "third_party_notices",
    ".gitkeep",
    ".dirinfo",
    ".pyformat_cache.json",
    "simz.json",
    "copyright",
}

JUNK_EXTENSIONS = {".tmp", ".bak", ".log", ".pyc"}


def empty_it(path: Path) -> None:
    """Empty a file's contents."""
    try:
        path.write_text("", encoding="utf-8")
    except OSError as e:
        print(f"Error emptying {path}: {e}", file=sys.stderr)


def remove_it(path: Path) -> None:
    """Remove a file or directory."""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as e:
        print(f"Error removing {path}: {e}", file=sys.stderr)


def should_skip(path: Path) -> bool:
    """Check if path should be skipped."""
    return any(skip_dir in path.parts for skip_dir in SKIP_DIRS)


def main() -> None:
    cwd = Path.cwd()
    removed_count = 0

    for path in cwd.rglob("*"):
        # Skip directories early
        if should_skip(path):
            continue

        loname = path.name.lower()
        rel_path = path.relative_to(cwd)

        # Check exact junk file matches first
        if loname in JUNK_FILES:
            remove_it(path)
            print(f"{rel_path} removed.")
            removed_count += 1
            continue

        # Check file extensions for temp/backup files
        if path.is_file() and any(loname.endswith(ext) for ext in JUNK_EXTENSIONS):
            remove_it(path)
            print(rel_path)
            removed_count += 1
            continue

        # Check for licenses directory in dist-info
        if path.is_dir() and loname == "licenses" and "dist-info" in path.parent.name:
            remove_it(path)
            print(rel_path)
            removed_count += 1
            continue

        # Handle partial matches (e.g., "license" in filename)
        if any(junk in loname for junk in JUNK_FILES):
            if REMOVE_MODE:
                remove_it(path)
            else:
                empty_it(path)
            print(rel_path)
            removed_count += 1

    if removed_count:
        print(f"\n{removed_count} item(s) removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
