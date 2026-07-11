#!/usr/bin/env python3
"""
Recursive file compression/decompression tool using Zstandard.
Compresses files in current directory recursively, skipping certain extensions and .git folders.
Uses Path.walk() for memory-efficient traversal (Python 3.13+).
"""

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import zstandard as zstd
import threading
import fnmatch
import json

# Extensions to skip during compression (already compressed or not worth compressing)
SKIP_EXTENSIONS_COMPRESS = {
    # Archive formats
    ".xz",
    ".gz",
    ".7z",
    ".zip",
    ".whl",
    ".lz4",
    ".zst",
    ".br",
    ".bz2",
    ".lzma",
    ".z",
    ".rar",
    ".tar",
    ".tgz",
    ".tbz2",
    # Image formats (already compressed)
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".svg",
    ".ico",
    ".heic",
    ".heif",
    ".avif",
    # Video formats (already compressed)
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".ogv",
    ".ts",
    ".m2ts",
    # Audio formats (already compressed)
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".wma",
    ".m4a",
    ".opus",
    ".mid",
    ".midi",
    ".aiff",
    # Document formats (already compressed)
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".odt",
    ".ods",
    ".odp",
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    # Other binary formats
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".iso",
    ".img",
    ".deb",
    ".rpm",
    ".pkg",
    ".msi",
}

# Extensions to skip during decompression (only process .zst files)
VALID_DECOMPRESS_EXTENSIONS = {".zst"}

# Directories to skip entirely
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".egg-info",  # Editable package metadata
    "dist",
    "build",
}

# Patterns for editable package directories to skip
SKIP_DIR_PATTERNS = [
    "*.egg-info",  # Editable package metadata directories
    "*.dist-info",  # Package distribution info
]


# Thread-safe counters for space reporting
class SpaceStats:
    def __init__(self):
        self.original_size = 0
        self.compressed_size = 0
        self.lock = threading.Lock()

    def add(self, original: int, compressed: int):
        with self.lock:
            self.original_size += original
            self.compressed_size += compressed

    def get_savings(self):
        if self.original_size == 0:
            return 0, 0, 0
        saved = self.original_size - self.compressed_size
        ratio = (self.compressed_size / self.original_size) * 100 if self.original_size > 0 else 0
        percent_saved = (saved / self.original_size) * 100 if self.original_size > 0 else 0
        return saved, ratio, percent_saved


def should_skip_directory(dir_name: str) -> bool:
    """Check if a directory should be skipped."""
    # Check exact matches
    if dir_name in SKIP_DIRS:
        return True

    # Check patterns
    for pattern in SKIP_DIR_PATTERNS:
        if fnmatch.fnmatch(dir_name, pattern):
            return True

    return False


def is_editable_package_dir(root_path: Path) -> bool:
    """
    Check if a directory contains editable package markers.
    Returns True if it's likely an editable installation directory.
    """
    try:
        # Check for .egg-info directory which indicates editable install
        for item in root_path.iterdir():
            if item.is_dir() and item.name.endswith(".egg-info"):
                # Check if it has the SOURCES.txt or PKG-INFO which indicates editable
                egg_info_path = item / "SOURCES.txt"
                if egg_info_path.exists():
                    return True
                # Also check for direct_url.json which indicates editable installs
                direct_url = item / "direct_url.json"
                if direct_url.exists():
                    try:
                        with open(direct_url, "r") as f:
                            data = json.load(f)
                            if data.get("dir_info", {}).get("editable", False):
                                return True
                    except:
                        pass
        return False
    except (PermissionError, OSError):
        return False


def get_files(directory: Path, compress: bool):
    """
    Recursively get files to process using Path.walk() for memory efficiency.
    Skips .git directories, symlinks, and unwanted extensions.
    """
    files = []
    total_dirs = 0
    total_files = 0
    skipped_symlinks = 0
    skipped_extensions = 0
    skipped_editable = 0
    skipped_dirs = 0
    skipped_media = 0

    # Using Path.walk() which yields (root, dirs, files) lazily
    for root, dirs, file_names in directory.walk():
        root_path = Path(root)

        # Check for .git in path
        if ".git" in root_path.parts:
            continue

        # Filter out directories to skip
        dirs_to_remove = []
        for dir_name in dirs:
            if should_skip_directory(dir_name):
                dirs_to_remove.append(dir_name)
                skipped_dirs += 1

        # Remove skipped directories from traversal
        for dir_name in dirs_to_remove:
            dirs.remove(dir_name)

        # Check if this is an editable package directory (site-packages with editable installs)
        if is_editable_package_dir(root_path):
            # Skip this directory entirely
            # Clear dirs to prevent traversal
            dirs.clear()
            skipped_editable += 1
            continue

        total_dirs += 1

        for file_name in file_names:
            file_path = root_path / file_name

            # Skip symlinks
            if file_path.is_symlink():
                skipped_symlinks += 1
                continue

            # Additional check for .egg-info files (metadata files)
            if ".egg-info" in str(file_path) or ".dist-info" in str(file_path):
                skipped_extensions += 1
                continue

            if compress:
                # During compression: skip files with unwanted extensions
                if file_path.suffix.lower() in SKIP_EXTENSIONS_COMPRESS:
                    skipped_extensions += 1
                    # Count media files specifically for reporting
                    if file_path.suffix.lower() in {
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".gif",
                        ".bmp",
                        ".tiff",
                        ".tif",
                        ".webp",
                        ".svg",
                        ".ico",
                        ".heic",
                        ".heif",
                        ".avif",
                        ".mp4",
                        ".mkv",
                        ".avi",
                        ".mov",
                        ".wmv",
                        ".flv",
                        ".webm",
                        ".m4v",
                        ".mpg",
                        ".mpeg",
                        ".3gp",
                        ".ogv",
                        ".ts",
                        ".m2ts",
                        ".mp3",
                        ".wav",
                        ".flac",
                        ".aac",
                        ".ogg",
                        ".wma",
                        ".m4a",
                        ".opus",
                        ".mid",
                        ".midi",
                        ".aiff",
                        ".pdf",
                        ".docx",
                        ".pptx",
                        ".xlsx",
                        ".odt",
                        ".ods",
                        ".odp",
                        ".epub",
                        ".mobi",
                        ".azw",
                        ".azw3",
                    }:
                        skipped_media += 1
                    continue
            else:
                # During decompression: only process .zst files
                if file_path.suffix not in VALID_DECOMPRESS_EXTENSIONS:
                    skipped_extensions += 1
                    continue

            files.append(file_path)
            total_files += 1

    if skipped_symlinks > 0:
        print(f"⚠️  Skipped {skipped_symlinks} symlinks")
    if skipped_media > 0:
        print(f"ℹ️  Skipped {skipped_media} media/binary files (already compressed)")
    if skipped_extensions > 0:
        print(f"ℹ️  Skipped {skipped_extensions} files with unwanted extensions")
    if skipped_editable > 0:
        print(f"ℹ️  Skipped {skipped_editable} editable package directories")
    if skipped_dirs > 0:
        print(f"ℹ️  Skipped {skipped_dirs} excluded directories")
    print(f"Scanned {total_dirs} directories, found {total_files} files to process")
    return files


def compress_file(
    input_path: Path,
    output_path: Path,
    level: int = 3,
    threads: int = 4,
    remove_original: bool = False,
    stats: SpaceStats = None,
):
    """Compress a single file using streaming compression."""
    try:
        # Get original size
        original_size = input_path.stat().st_size

        # Create compressor
        compressor = zstd.ZstdCompressor(level=level, threads=threads)

        # Read input and compress in chunks
        with open(input_path, "rb") as infile:
            with open(output_path, "wb") as outfile:
                # Use streaming compression
                reader = compressor.stream_reader(infile)
                while True:
                    chunk = reader.read(8192)
                    if not chunk:
                        break
                    outfile.write(chunk)

        # Get compressed size
        compressed_size = output_path.stat().st_size

        # Update stats
        if stats:
            stats.add(original_size, compressed_size)

        # Remove original file if successful
        if remove_original:
            input_path.unlink()

        return True, input_path, output_path, original_size, compressed_size

    except Exception as e:
        # Clean up output file if compression failed
        if output_path.exists():
            try:
                output_path.unlink()
            except:
                pass
        return False, input_path, str(e), 0, 0


def decompress_file(
    input_path: Path, output_path: Path, threads: int = 4, remove_original: bool = False, stats: SpaceStats = None
):
    """Decompress a single file using streaming decompression."""
    try:
        # Get compressed size
        compressed_size = input_path.stat().st_size

        # Create decompressor
        decompressor = zstd.ZstdDecompressor()

        # Read input and decompress in chunks
        with open(input_path, "rb") as infile:
            with open(output_path, "wb") as outfile:
                # Use streaming decompression
                reader = decompressor.stream_reader(infile)
                while True:
                    chunk = reader.read(8192)
                    if not chunk:
                        break
                    outfile.write(chunk)

        # Get decompressed size
        decompressed_size = output_path.stat().st_size

        # Remove original compressed file if successful
        if remove_original:
            input_path.unlink()

        return True, input_path, output_path, decompressed_size, compressed_size

    except Exception as e:
        # Clean up output file if decompression failed
        if output_path.exists():
            try:
                output_path.unlink()
            except:
                pass
        return False, input_path, str(e), 0, 0


def format_size(bytes_size: int) -> str:
    """Format bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def process_files(files, compress: bool, level: int = 3, threads: int = 4, remove_original: bool = False):
    """Process files with progress display."""
    total = len(files)
    completed = 0
    failed = []
    skipped = 0
    stats = SpaceStats()

    print(f"\n{'Compressing' if compress else 'Decompressing'} {total} files...")
    print(f"Remove original files: {'Yes' if remove_original else 'No'}")
    print("-" * 60)

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {}

        for file_path in files:
            if compress:
                output_path = file_path.with_suffix(file_path.suffix + ".zst")
                # Skip if output already exists
                if output_path.exists():
                    print(f"⚠️  Skipping {file_path.name} - output already exists")
                    skipped += 1
                    completed += 1
                    continue
                future = executor.submit(compress_file, file_path, output_path, level, threads, remove_original, stats)
            else:
                # For decompression, remove .zst suffix
                output_path = file_path.with_suffix("")

                # Skip if output already exists
                if output_path.exists():
                    print(f"⚠️  Skipping {file_path.name} - output already exists")
                    skipped += 1
                    completed += 1
                    continue

                future = executor.submit(decompress_file, file_path, output_path, threads, remove_original, stats)

            futures[future] = (file_path, output_path)

        # Process completed tasks with progress
        for future in as_completed(futures):
            result = future.result()
            if compress:
                success, path, output_path, original_size, compressed_size = result
            else:
                success, path, output_path, decompressed_size, compressed_size = result

            completed += 1

            # Progress bar
            progress = int((completed / total) * 50)
            bar = "█" * progress + "░" * (50 - progress)
            print(f"\rProgress: [{bar}] {completed}/{total} files", end="", flush=True)

            if not success:
                failed.append((path, result[2] if len(result) > 2 else "Unknown error"))

    print("\n" + "-" * 60)

    # Summary
    if compress and total > 0:
        saved, ratio, percent_saved = stats.get_savings()
        print(f"\n📊 Compression Statistics:")
        print(f"   Original size:  {format_size(stats.original_size)}")
        print(f"   Compressed size: {format_size(stats.compressed_size)}")
        print(f"   Space saved:    {format_size(saved)} ({percent_saved:.1f}%)")
        print(f"   Compression ratio: {ratio:.1f}%")

    if skipped > 0:
        print(f"\n⚠️  Skipped {skipped} files (already exist or invalid format)")

    if failed:
        print(f"\n❌ Failed to process {len(failed)} files:")
        for path, error in failed:
            print(f"  - {path}: {error}")
    else:
        success_count = total - skipped
        if success_count > 0:
            print(f"\n✅ Successfully {'compressed' if compress else 'decompressed'} {success_count} files!")
            if remove_original:
                print(f"   Original files have been removed.")
        else:
            print("\n⚠️  No files were processed.")


def main():
    parser = argparse.ArgumentParser(description="Recursively compress or decompress files using Zstandard")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-c", "--compress", action="store_true", help="Compress files (default if no action specified)")
    group.add_argument("-d", "--decompress", action="store_true", help="Decompress files")
    parser.add_argument(
        "--level", type=int, default=11, choices=range(1, 23), help="Compression level (1-22, default: 11)"
    )
    parser.add_argument("--threads", type=int, default=4, help="Number of threads to use (default: 4)")
    parser.add_argument("--dir", type=str, default=".", help="Directory to process (default: current directory)")
    parser.add_argument("--keep", action="store_true", help="Keep original files (default: remove on success)")

    args = parser.parse_args()

    # Default to compress if no action specified
    if not args.compress and not args.decompress:
        args.compress = True
        print("No action specified, defaulting to compression mode")

    # Validate arguments
    if args.compress and (args.level < 1 or args.level > 22):
        print("Error: Compression level must be between 1 and 22")
        sys.exit(1)

    # Get directory
    base_dir = Path(args.dir).resolve()
    if not base_dir.exists():
        print(f"Error: Directory '{base_dir}' does not exist")
        sys.exit(1)

    if not base_dir.is_dir():
        print(f"Error: '{base_dir}' is not a directory")
        sys.exit(1)

    # Remove original files by default (unless --keep is specified)
    remove_original = not args.keep

    print(f"Working directory: {base_dir}")
    print(f"Mode: {'Compression' if args.compress else 'Decompression'}")
    print(f"Threads: {args.threads}")
    if args.compress:
        print(f"Compression level: {args.level}")
    print(f"Keep original files: {'Yes' if args.keep else 'No'}")

    # Get files to process
    print("\nScanning directory tree...")
    files = get_files(base_dir, args.compress)

    if not files:
        print("No files to process.")
        return

    # Process files
    process_files(files, args.compress, args.level, args.threads, remove_original)


if __name__ == "__main__":
    main()
