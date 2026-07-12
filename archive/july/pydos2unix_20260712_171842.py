#!/data/data/com.termux/files/usr/bin/env python
"""
A Linux dos2unix command implementation in Python.
Converts DOS/Windows line endings (CRLF) to Unix line endings (LF).

Features:
- Uses pathlib for cross-platform path handling
- Parallel processing for memory efficiency
- In-place file updates
- Accepts multiple files/folders as input
- Processes current directory recursively if no input is given
- Memory-optimized chunk-based reading/writing
"""

import argparse
import sys
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import List, Tuple, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CHUNK_SIZE = 8192  # 8KB chunks for memory efficiency
BINARY_EXTENSIONS = {
    '.bin', '.exe', '.dll', '.so', '.o', '.a', '.pyc',
    '.jar', '.class', '.zip', '.tar', '.gz', '.7z', '.rar',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
    '.mp3', '.mp4', '.avi', '.mkv', '.flv', '.mov', '.wav',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
}

# Text file extensions to prioritize (None means process all text files)
TEXT_EXTENSIONS = {
    '.txt', '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp',
    '.cs', '.php', '.rb', '.go', '.rs', '.sh', '.bash', '.zsh', '.ksh',
    '.conf', '.cfg', '.ini', '.yaml', '.yml', '.json', '.xml', '.html',
    '.htm', '.css', '.scss', '.sql', '.md', '.markdown', '.rst', '.tex',
    '.log', '.csv', '.tsv', '.gradle', '.maven', '.cmake', '.makefile'
}


def is_text_file(file_path: Path) -> bool:
    """
    Determine if a file is a text file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file is text, False if binary
    """
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return False
    
    # If it's a known text extension, process it
    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    
    # For unknown extensions, try to detect binary by reading first bytes
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(512)
            # Check for null bytes (binary indicator)
            return b'\x00' not in chunk
    except (IOError, OSError):
        return False


def convert_dos_to_unix_chunk(chunk: bytes) -> bytes:
    """
    Convert DOS/Windows line endings to Unix in a byte chunk.
    
    Args:
        chunk: Byte chunk to process
        
    Returns:
        Chunk with converted line endings
    """
    # Replace CRLF (\r\n) with LF (\n)
    # Use a simple byte replacement for efficiency
    return chunk.replace(b'\r\n', b'\n')


def convert_file(file_path: Path) -> Tuple[str, bool, str]:
    """
    Convert a single file from DOS to Unix line endings.
    
    Args:
        file_path: Path to the file to convert
        
    Returns:
        Tuple of (file_path, success, message)
    """
    try:
        # Check if file is readable and text
        if not file_path.is_file():
            return (str(file_path), False, "Not a file")
        
        if not is_text_file(file_path):
            return (str(file_path), False, "Binary file (skipped)")
        
        # Read file in chunks for memory efficiency
        converted = False
        temp_data = bytearray()
        
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    converted_chunk = convert_dos_to_unix_chunk(chunk)
                    if converted_chunk != chunk:
                        converted = True
                    
                    temp_data.extend(converted_chunk)
            
            # Only write if changes were made
            if converted:
                with open(file_path, 'wb') as f:
                    f.write(temp_data)
                return (str(file_path), True, "Converted")
            else:
                return (str(file_path), True, "Already Unix format")
        
        except (IOError, OSError) as e:
            return (str(file_path), False, f"Read/Write error: {e}")
    
    except Exception as e:
        return (str(file_path), False, f"Error: {e}")


def find_text_files(paths: List[Path]) -> List[Path]:
    """
    Find all text files in given paths.
    
    Args:
        paths: List of file/folder paths to process
        
    Returns:
        List of text file paths
    """
    files = []
    
    for path in paths:
        if path.is_file():
            if is_text_file(path):
                files.append(path)
        elif path.is_dir():
            # Recursively find all text files
            for text_file in path.rglob('*'):
                if text_file.is_file() and is_text_file(text_file):
                    files.append(text_file)
    
    return files


def get_input_paths(input_args: Optional[List[str]]) -> List[Path]:
    """
    Get input paths from command line arguments.
    
    Args:
        input_args: List of file/folder paths, or None for current directory
        
    Returns:
        List of Path objects
    """
    if not input_args:
        # Process current directory recursively
        return [Path.cwd()]
    
    paths = []
    for arg in input_args:
        path = Path(arg).resolve()
        if path.exists():
            paths.append(path)
        else:
            logger.warning(f"Path does not exist: {arg}")
    
    return paths


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert DOS/Windows line endings (CRLF) to Unix (LF)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.txt
  %(prog)s file1.txt file2.txt file3.txt
  %(prog)s /path/to/folder
  %(prog)s /path/to/folder file.txt
  %(prog)s                    # Process current directory recursively
        """
    )
    
    parser.add_argument(
        'paths',
        nargs='*',
        help='Files or folders to process (default: current directory)'
    )
    
    parser.add_argument(
        '-j', '--jobs',
        type=int,
        default=cpu_count(),
        help=f'Number of parallel jobs (default: {cpu_count()})'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress output messages'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed output for each file'
    )
    
    args = parser.parse_args()
    
    # Get input paths
    input_paths = get_input_paths(args.paths if args.paths else None)
    
    if not input_paths:
        logger.error("No valid paths provided")
        return 1
    
    # Find all text files
    files_to_process = find_text_files(input_paths)
    
    if not files_to_process:
        if not args.quiet:
            logger.info("No text files found to process")
        return 0
    
    if not args.quiet and not args.verbose:
        logger.info(f"Processing {len(files_to_process)} file(s) with {args.jobs} worker(s)...")
    
    # Process files in parallel
    converted_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        with Pool(processes=args.jobs) as pool:
            results = pool.map(convert_file, files_to_process)
        
        for file_path, success, message in results:
            if args.verbose:
                status = "✓" if success else "✗"
                print(f"{status} {file_path}: {message}")
            
            if success:
                if "Converted" in message:
                    converted_count += 1
                else:
                    skipped_count += 1
            else:
                error_count += 1
        
        # Summary
        if not args.quiet:
            print()
            logger.info(f"Converted: {converted_count} file(s)")
            logger.info(f"Already Unix format: {skipped_count} file(s)")
            if error_count > 0:
                logger.warning(f"Errors: {error_count} file(s)")
        
        return 0 if error_count == 0 else 1
    
    except KeyboardInterrupt:
        logger.error("\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
