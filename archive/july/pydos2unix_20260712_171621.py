#!/data/data/com.termux/files/usr/bin/env python


"""
dos2unix implementation in Python
Converts CRLF (Windows) line endings to LF (Unix)
Skips binary files automatically
Uses multiprocessing for speed
"""

import argparse
import sys
import time
from functools import partial
from multiprocessing import Pool, cpu_count
from pathlib import Path

import magic

SKIP_DIRS = frozenset({"lazy", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"})


def is_binary_file(file_path: Path) -> bool:
    try:
        mime = magic.from_file(str(file_path), mime=True)
        text_mimes = {
            "text/plain",
            "text/x-python",
            "text/x-script",
            "text/x-c",
            "text/x-c++",
            "text/x-java",
            "text/html",
            "text/xml",
            "text/css",
            "text/javascript",
            "text/x-sh",
            "text/x-perl",
            "text/x-ruby",
            "text/x-markdown",
        }
        if mime not in text_mimes and not mime.startswith("text/"):
            return True
    except (ImportError, Exception):
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return True
        except Exception:
            return True
    try:
        with open(file_path, "rb") as f:
            first_chunk = f.read(8192)
            if b"\r\n" not in first_chunk and b"\r" not in first_chunk:
                return True
    except Exception:
        return True
    return False


def convert_file(file_path: Path, dry_run: bool = False, force: bool = False) -> dict:
    result = {"file": str(file_path), "status": "unchanged", "size_diff": 0, "error": None}
    try:
        if not force and is_binary_file(file_path):
            result["status"] = "skipped_binary"
            return result
        with open(file_path, "rb") as f:
            content = f.read()
        original_size = len(content)
        if b"\r\n" not in content and b"\r" not in content:
            result["status"] = "unchanged"
            return result
        converted = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        new_size = len(converted)
        if original_size == new_size:
            result["status"] = "unchanged"
            return result
        if not dry_run:
            with open(file_path, "wb") as f:
                f.write(converted)
        result["status"] = "converted"
        result["size_diff"] = original_size - new_size
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


def process_files(files: list, dry_run: bool = False, force: bool = False, num_workers: int = None) -> dict:
    if not files:
        return {"total": 0, "converted": 0, "skipped": 0, "errors": 0, "size_saved": 0, "files": []}
    if num_workers is None:
        num_workers = min(cpu_count(), len(files))
    convert_func = partial(convert_file, dry_run=dry_run, force=force)
    stats = {
        "total": len(files),
        "converted": 0,
        "skipped_binary": 0,
        "unchanged": 0,
        "errors": 0,
        "size_saved": 0,
        "files": [],
    }
    with Pool(processes=num_workers) as pool:
        results = pool.map(convert_func, files)
    for result in results:
        stats["files"].append(result)
        if result["status"] == "converted":
            stats["converted"] += 1
            stats["size_saved"] += result["size_diff"]
        elif result["status"] == "skipped_binary":
            stats["skipped_binary"] += 1
        elif result["status"] == "unchanged":
            stats["unchanged"] += 1
        elif result["status"] == "error":
            stats["errors"] += 1
    return stats


def find_files(paths: list, recursive: bool = False, exclude_hidden: bool = True) -> list:
    files = []
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            print(f"Warning: {path} does not exist", file=sys.stderr)
            continue
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            if recursive:
                pattern = "**/*" if not exclude_hidden else "**/[!.]*"
                for p in path.glob(pattern):
                    if p.is_file():
                        if exclude_hidden and any(part.startswith(".") for part in p.parts):
                            continue
                        files.append(p)
            else:
                for p in path.glob("*"):
                    if p.is_file():
                        if exclude_hidden and p.name.startswith("."):
                            continue
                        files.append(p)
    seen = set()
    unique_files = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    return unique_files


def print_stats(stats: dict, dry_run: bool = False) -> None:
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN' if dry_run else 'CONVERSION COMPLETE'}")
    print(f"{'=' * 60}")
    print(f"Total files processed: {stats['total']}")
    print(f"  - Converted: {stats['converted']}")
    print(f"  - Already Unix format: {stats['unchanged']}")
    print(f"  - Skipped (binary): {stats['skipped_binary']}")
    print(f"  - Errors: {stats['errors']}")
    if stats["size_saved"] > 0:
        size_saved_mb = stats["size_saved"] / (1024 * 1024)
        print(f"\nTotal space saved: {size_saved_mb:.2f} MB")
    if stats["errors"] > 0:
        print("\nErrors:")
        for result in stats["files"]:
            if result["status"] == "error":
                print(f"  {result['file']}: {result['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert CRLF (Windows) line endings to LF (Unix)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.txt                    # Convert single file
  %(prog)s -r directory/               # Convert all files in directory recursively
  %(prog)s -r --force directory/       # Force convert binary files too
  %(prog)s -r --dry-run directory/     # Preview changes without converting
  %(prog)s file1.txt file2.txt file3.txt  # Multiple files
        """,
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to convert")
    parser.add_argument("-r", "--recursive", action="store_true", help="Process directories recursively")
    parser.add_argument("-f", "--force", action="store_true", help="Force conversion of binary files (not recommended)")
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Show what would be changed without actually converting"
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=None, help=f"Number of parallel jobs (default: CPU count = {cpu_count()})"
    )
    parser.add_argument("--no-hidden", action="store_true", default=True, help="Exclude hidden files/directories")
    parser.add_argument(
        "--include-hidden", dest="no_hidden", action="store_false", help="Include hidden files/directories"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress per-file output")
    args = parser.parse_args()
    print("Scanning for files...")
    files = find_files(args.paths, args.recursive, args.no_hidden)
    if not files:
        print("No files found to process.")
        return 1
    print(f"Found {len(files)} files to process")
    if args.dry_run:
        print("DRY RUN MODE: No changes will be made")
    start_time = time.time()
    stats = process_files(files, args.dry_run, args.force, args.jobs)
    elapsed_time = time.time() - start_time
    if not args.quiet:
        print("\nConversion results:")
        for result in stats["files"]:
            if result["status"] == "converted":
                print(f"  ✓ {result['file']} (saved {result['size_diff']} bytes)")
            elif result["status"] == "skipped_binary" and not args.quiet:
                print(f"  ⊘ {result['file']} (binary, skipped)")
            elif result["status"] == "error":
                print(f"  ✗ {result['file']}: {result['error']}")
    print_stats(stats, args.dry_run)
    print(f"\nTime elapsed: {elapsed_time:.2f} seconds")
    print(f"Processing speed: {len(files) / elapsed_time:.1f} files/second")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
