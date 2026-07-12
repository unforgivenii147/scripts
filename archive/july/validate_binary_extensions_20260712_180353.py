#!/data/data/com.termux/files/usr/bin/env python
"""
Sanity check script to validate binary file extensions.
Traverses the filesystem to find files with extensions in BIN_EXT,
verifies they are actually binary files, and reports mismatches.
Uses memory-efficient os.walk traversal with progress reporting.
"""

import os
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import Tuple, Iterator, Set
import logging
import mimetypes

from dh import BIN_EXT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SpinnerProgressReporter:
    """Progress reporter with spinner animation for Termux/Linux."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.last_count = 0
        self.spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_index = 0
    
    def __call__(self, current_path: str, file_count: int):
        """Report progress with spinner."""
        if not self.verbose:
            return
        
        if file_count - self.last_count >= 500:
            self.last_count = file_count
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner)
            path_display = current_path[:60] + "..." if len(current_path) > 60 else current_path
            
            msg = (
                f"\r{self.spinner[self.spinner_index]} "
                f"Files: {file_count:8d} | {path_display}"
            )
            print(msg, end='', flush=True)


def memory_efficient_file_finder(
    root_dir: str,
    extensions: Set[str],
    progress_callback=None,
    skip_symlinks: bool = True,
    skip_mount_points: bool = True
) -> Iterator[Path]:
    """
    Memory-efficient file finder using os.walk instead of pathlib.rglob.
    Prevents loading entire directory trees into memory.
    
    Args:
        root_dir: Root directory to traverse
        extensions: Set of file extensions to match (lowercase, with dots)
        progress_callback: Optional callback function(current_path, file_count) for progress
        skip_symlinks: Skip symbolic links to prevent loops
        skip_mount_points: Skip different filesystems
        
    Yields:
        Path objects matching the extensions
    """
    extensions_lower = {ext.lower() for ext in extensions}
    visited_inodes = set()
    file_count = 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(
            root_dir,
            topdown=True,
            onerror=lambda e: logger.warning(f"Walk error: {e}")
        ):
            try:
                dir_stat = os.stat(dirpath)
                dir_inode = (dir_stat.st_dev, dir_stat.st_ino)
                
                # Skip if already visited (detects symlink loops)
                if skip_symlinks and dir_inode in visited_inodes:
                    dirnames[:] = []
                    continue
                
                visited_inodes.add(dir_inode)
                
                # Skip different filesystems
                if skip_mount_points and dirpath != root_dir:
                    try:
                        root_stat = os.stat(root_dir)
                        if dir_stat.st_dev != root_stat.st_dev:
                            dirnames[:] = []
                            continue
                    except OSError:
                        pass
                
            except (OSError, FileNotFoundError):
                dirnames[:] = []
                continue
            
            # Progress update
            if progress_callback and file_count % 500 == 0:
                progress_callback(dirpath, file_count)
            
            for filename in filenames:
                try:
                    file_path = Path(dirpath) / filename
                    
                    if file_path.suffix.lower() in extensions_lower:
                        file_count += 1
                        yield file_path
                except (OSError, FileNotFoundError):
                    continue
    
    except KeyboardInterrupt:
        logger.info("Traversal interrupted by user")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during traversal: {e}")


def is_binary_file(file_path: Path) -> bool:
    """
    Determine if a file is binary by checking content.
    
    Args:
        file_path: Path object to the file
        
    Returns:
        True if file appears to be binary, False if text, None if error
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)  # Read first 8KB
        
        if not chunk:  # Empty file
            return None
        
        # Check for null bytes (strong indicator of binary)
        if b'\x00' in chunk:
            return True
        
        # Check for high proportion of non-text bytes
        non_text_chars = sum(1 for byte in chunk if byte < 0x20 and byte not in (0x09, 0x0A, 0x0D))
        if len(chunk) > 0:
            non_text_ratio = non_text_chars / len(chunk)
            if non_text_ratio > 0.3:  # More than 30% non-text bytes
                return True
        
        # Try to decode as text
        try:
            chunk.decode('utf-8')
            return False
        except UnicodeDecodeError:
            # Try other common encodings
            for encoding in ['latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    chunk.decode(encoding)
                    return False
                except (UnicodeDecodeError, LookupError):
                    continue
            # If all decodings fail, likely binary
            return True
            
    except (OSError, IOError, PermissionError):
        return None  # File access error


def check_file(file_path: Path) -> Tuple[Path, str, bool, str]:
    """
    Check if a file with BIN_EXT extension is actually binary.
    
    Args:
        file_path: Path object to the file
        
    Returns:
        Tuple of (file_path, extension, is_binary, mime_type)
    """
    try:
        extension = file_path.suffix.lower()
        is_binary = is_binary_file(file_path)
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "unknown"
        
        return (file_path, extension, is_binary, mime_type)
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return (file_path, file_path.suffix.lower(), None, "error")


def validate_extensions(root_dir: str = '/', num_workers: int = None, verbose: bool = True) -> dict:
    """
    Main validation function using memory-efficient traversal.
    
    Args:
        root_dir: Root directory to start traversal (default: '/')
        num_workers: Number of parallel processes (default: cpu_count - 1)
        verbose: Show progress (default: True)
        
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
    logger.info(f"Looking for extensions: {sorted(BIN_EXT)}")
    logger.info(f"Using {num_workers} worker processes")
    print()  # Blank line for progress output
    
    # Memory-efficient file discovery
    progress = SpinnerProgressReporter(verbose=verbose)
    matching_files = list(memory_efficient_file_finder(
        root_dir,
        BIN_EXT,
        progress_callback=progress,
        skip_symlinks=True,
        skip_mount_points=True
    ))
    print()  # Clear spinner line
    logger.info(f"Found {len(matching_files)} files with target extensions")
    
    if not matching_files:
        logger.warning("No files found with specified extensions")
        return {
            'total_files': 0,
            'binary_files': 0,
            'text_files': 0,
            'access_errors': 0,
            'mismatches': [],
            'by_extension': {}
        }
    
    # Process files in parallel
    logger.info("Checking file types (parallel processing)...")
    with Pool(num_workers) as pool:
        results = pool.map(check_file, matching_files)
    
    # Analyze results
    binary_count = 0
    text_count = 0
    error_count = 0
    mismatches = []
    by_extension = {}
    
    for file_path, ext, is_binary, mime_type in results:
        if ext not in by_extension:
            by_extension[ext] = {'binary': 0, 'text': 0, 'error': 0, 'files': []}
        
        by_extension[ext]['files'].append({
            'path': str(file_path),
            'is_binary': is_binary,
            'mime_type': mime_type
        })
        
        if is_binary is True:
            binary_count += 1
            by_extension[ext]['binary'] += 1
        elif is_binary is False:
            text_count += 1
            by_extension[ext]['text'] += 1
            mismatches.append({
                'path': str(file_path),
                'extension': ext,
                'mime_type': mime_type
            })
        else:
            error_count += 1
            by_extension[ext]['error'] += 1
    
    return {
        'total_files': len(matching_files),
        'binary_files': binary_count,
        'text_files': text_count,
        'access_errors': error_count,
        'mismatches': mismatches,
        'by_extension': by_extension
    }


def print_report(results: dict):
    """Print a formatted report of validation results."""
    print("\n" + "=" * 80)
    print("BINARY EXTENSION VALIDATION REPORT")
    print("=" * 80)
    
    print(f"\nSummary:")
    print(f"  Total files found:    {results['total_files']}")
    print(f"  Actual binary files:  {results['binary_files']}")
    print(f"  Text files:           {results['text_files']}")
    print(f"  Access errors:        {results['access_errors']}")
    
    if results['mismatches']:
        print(f"\n⚠️  MISMATCHES FOUND: {len(results['mismatches'])} files with binary extension are actually TEXT files")
        print("-" * 80)
        for i, mismatch in enumerate(results['mismatches'][:20], 1):  # Show first 20
            print(f"  {i}. {mismatch['path']}")
            print(f"     └─ Extension: {mismatch['extension']} | MIME: {mismatch['mime_type']}")
        if len(results['mismatches']) > 20:
            print(f"  ... and {len(results['mismatches']) - 20} more")
    else:
        print(f"\n✓ No mismatches found! All files match their extensions.")
    
    print(f"\nBreakdown by extension:")
    print("-" * 80)
    for ext, stats in sorted(results['by_extension'].items()):
        print(f"  {ext:12} - Binary: {stats['binary']:6}  Text: {stats['text']:6}  Errors: {stats['error']:6}")
    
    print("\n" + "=" * 80)


if __name__ == '__main__':
    import sys
    
    # Optional: specify root directory from command line
    root_dir = sys.argv[1] if len(sys.argv) > 1 else '/'
    
    try:
        # Run validation
        results = validate_extensions(root_dir, verbose=True)
        
        # Print report
        print_report(results)
        
        # Exit with error code if mismatches found
        sys.exit(1 if results['mismatches'] else 0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Validation stopped by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
