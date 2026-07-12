#!/data/data/com.termux/files/usr/bin/env python
"""
Sanity check script to validate text file extensions.
Traverses the filesystem to find files with extensions in TXT_EXT,
verifies they are actually text-based files, and reports mismatches.
"""

import mimetypes
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import Tuple, List
import logging
from collections import defaultdict

from dh import TXT_EXT

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def is_text_file(file_path: Path) -> bool:
    """
    Determine if a file is text-based by checking MIME type.

    Args:
        file_path: Path object to the file

    Returns:
        True if file appears to be text-based, False otherwise
    """
    try:
        # Try to read first few bytes to detect binary content
        with open(file_path, "rb") as f:
            chunk = f.read(8192)  # Read first 8KB

        # Check for null bytes (common in binary files)
        if b"\x00" in chunk:
            return False

        # Try to decode as UTF-8
        try:
            chunk.decode("utf-8")
            return True
        except UnicodeDecodeError:
            # Try other common encodings
            for encoding in ["latin-1", "iso-8859-1", "cp1252"]:
                try:
                    chunk.decode(encoding)
                    return True
                except (UnicodeDecodeError, LookupError):
                    continue
            return False

    except (OSError, IOError, PermissionError):
        return None  # File access error


def check_file(file_path: Path) -> Tuple[Path, str, bool, str]:
    """
    Check if a file with TXT_EXT extension is actually text-based.

    Args:
        file_path: Path object to the file

    Returns:
        Tuple of (file_path, extension, is_text, mime_type)
    """
    try:
        extension = file_path.suffix.lower()
        is_text = is_text_file(file_path)
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "unknown"

        return (file_path, extension, is_text, mime_type)
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return (file_path, file_path.suffix.lower(), None, "error")


def find_files_with_extensions(root_dir: Path, extensions: set, max_depth: int = None) -> List[Path]:
    """
    Find all files with specified extensions under root directory.

    Args:
        root_dir: Root directory to start traversal
        extensions: Set of file extensions to search for (with dots, e.g., {'.txt', '.md'})
        max_depth: Maximum directory depth to traverse (None for unlimited)

    Returns:
        List of Path objects matching the extensions
    """
    matching_files = []
    extensions_lower = {ext.lower() for ext in extensions}

    try:
        for path in root_dir.rglob("*"):
            if path.is_file():
                if path.suffix.lower() in extensions_lower:
                    matching_files.append(path)
    except PermissionError as e:
        logger.warning(f"Permission denied accessing {root_dir}: {e}")

    return matching_files


def validate_extensions(root_dir: str = "/", num_workers: int = None) -> dict:
    """
    Main validation function.

    Args:
        root_dir: Root directory to start traversal (default: '/')
        num_workers: Number of parallel processes (default: cpu_count)

    Returns:
        Dictionary with validation results
    """
    if num_workers is None:
        num_workers = max(1, cpu_count() - 1)

    root_path = Path(root_dir)

    if not root_path.exists():
        logger.error(f"Root directory {root_dir} does not exist")
        return {}

    logger.info(f"Starting filesystem traversal from {root_dir}...")
    logger.info(f"Looking for extensions: {sorted(TXT_EXT)}")
    logger.info(f"Using {num_workers} worker processes")

    # Find all files with TXT_EXT extensions
    matching_files = find_files_with_extensions(root_path, TXT_EXT)
    logger.info(f"Found {len(matching_files)} files with target extensions")

    if not matching_files:
        logger.warning("No files found with specified extensions")
        return {
            "total_files": 0,
            "text_files": 0,
            "binary_files": 0,
            "access_errors": 0,
            "mismatches": [],
            "by_extension": {},
        }

    # Process files in parallel
    logger.info("Checking file types...")
    with Pool(num_workers) as pool:
        results = pool.map(check_file, matching_files)

    # Analyze results
    text_count = 0
    binary_count = 0
    error_count = 0
    mismatches = []
    by_extension = defaultdict(lambda: {"text": 0, "binary": 0, "error": 0, "files": []})

    for file_path, ext, is_text, mime_type in results:
        by_extension[ext]["files"].append({"path": str(file_path), "is_text": is_text, "mime_type": mime_type})

        if is_text is True:
            text_count += 1
            by_extension[ext]["text"] += 1
        elif is_text is False:
            binary_count += 1
            by_extension[ext]["binary"] += 1
            mismatches.append({"path": str(file_path), "extension": ext, "mime_type": mime_type})
        else:
            error_count += 1
            by_extension[ext]["error"] += 1

    return {
        "total_files": len(matching_files),
        "text_files": text_count,
        "binary_files": binary_count,
        "access_errors": error_count,
        "mismatches": mismatches,
        "by_extension": dict(by_extension),
    }


def print_report(results: dict):
    """Print a formatted report of validation results."""
    print("\n" + "=" * 80)
    print("TEXT EXTENSION VALIDATION REPORT")
    print("=" * 80)

    print(f"\nSummary:")
    print(f"  Total files found:    {results['total_files']}")
    print(f"  Actual text files:    {results['text_files']}")
    print(f"  Binary files:         {results['binary_files']}")
    print(f"  Access errors:        {results['access_errors']}")

    if results["mismatches"]:
        print(f"\n⚠️  MISMATCHES FOUND: {len(results['mismatches'])} files with .txt extension are NOT text files")
        print("-" * 80)
        for mismatch in results["mismatches"][:20]:  # Show first 20
            print(f"  {mismatch['path']}")
            print(f"    Extension: {mismatch['extension']}")
            print(f"    MIME type: {mismatch['mime_type']}")
        if len(results["mismatches"]) > 20:
            print(f"  ... and {len(results['mismatches']) - 20} more")
    else:
        print(f"\n✓ No mismatches found! All files match their extensions.")

    print(f"\nBreakdown by extension:")
    print("-" * 80)
    for ext, stats in sorted(results["by_extension"].items()):
        print(f"  {ext:12} - Text: {stats['text']:6}  Binary: {stats['binary']:6}  Errors: {stats['error']:6}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    import sys

    # Optional: specify root directory from command line
    root_dir = sys.argv[1] if len(sys.argv) > 1 else "/"

    # Run validation
    results = validate_extensions(root_dir)

    # Print report
    print_report(results)

    # Exit with error code if mismatches found
    sys.exit(1 if results["mismatches"] else 0)
