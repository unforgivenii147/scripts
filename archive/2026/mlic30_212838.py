#!/data/data/com.termux/files/usr/bin/env python
"""
Find repeated multiline strings in text files recursively.
Supports parallel processing, removal, and saving of found strings.
"""

import argparse
import concurrent.futures
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import sys

# Minimum length for a multiline string to be considered
MIN_LINES = 2
MIN_CHARS = 10


def find_multiline_strings(
    file_path: Path, min_lines: int = 2, min_chars: int = 10
) -> Dict[str, List[Tuple[int, int]]]:
    """
    Find all multiline strings in a file.

    Returns a dictionary with string content as key and list of (start_line, end_line) positions.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return {}

    strings = defaultdict(list)
    i = 0

    while i < len(lines):
        # Find start of a multiline string (non-empty line)
        if lines[i].strip():
            start = i
            string_lines = [lines[i]]
            i += 1

            # Collect consecutive non-empty lines
            while i < len(lines) and lines[i].strip():
                string_lines.append(lines[i])
                i += 1

            end = i - 1

            # Check if we have enough lines and characters
            full_string = "".join(string_lines)
            if len(string_lines) >= min_lines and len(full_string.strip()) >= min_chars:
                # Normalize the string for comparison (preserve original)
                normalized = normalize_string(full_string)
                strings[normalized].append((start, end))
        else:
            i += 1

    return strings


def normalize_string(text: str) -> str:
    """Normalize string for comparison by stripping trailing whitespace."""
    return "\n".join(line.rstrip() for line in text.splitlines())


def find_files(directory: Path, extensions: Optional[Set[str]] = None) -> List[Path]:
    """Recursively find text files in directory."""
    if extensions is None:
        # Common text file extensions
        extensions = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".html",
            ".css",
            ".xml",
            ".json",
            ".yaml",
            ".yml",
            ".csv",
            ".log",
            ".ini",
            ".cfg",
            ".conf",
            ".sh",
            ".bat",
            ".ps1",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".rb",
            ".php",
            ".sql",
        }

    files = []
    try:
        for item in directory.rglob("*"):
            if item.is_file() and item.suffix.lower() in extensions:
                files.append(item)
    except PermissionError:
        print(f"Permission denied accessing {directory}", file=sys.stderr)

    return files


def process_file(args: Tuple[Path, int, int, Optional[Set[str]]]) -> Tuple[Path, Dict[str, List[Tuple[int, int]]]]:
    """Process a single file to find multiline strings."""
    file_path, min_lines, min_chars, extensions = args
    strings = find_multiline_strings(file_path, min_lines, min_chars)
    return file_path, strings


def find_repeated_strings(
    directory: Path,
    min_lines: int = 2,
    min_chars: int = 10,
    max_workers: Optional[int] = None,
    extensions: Optional[Set[str]] = None,
) -> Dict[str, List[Tuple[Path, List[Tuple[int, int]]]]]:
    """
    Find multiline strings that repeat across files using parallel processing.

    Returns a dictionary with normalized string as key and list of (file, positions) tuples.
    """
    files = find_files(directory, extensions)

    if not files:
        print("No text files found in directory", file=sys.stderr)
        return {}

    print(f"Found {len(files)} files to process...")

    # Process files in parallel
    all_strings = defaultdict(list)

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Prepare arguments for each file
        args = [(f, min_lines, min_chars, extensions) for f in files]

        # Submit all tasks
        futures = {executor.submit(process_file, arg): arg[0] for arg in args}

        # Collect results
        for future in concurrent.futures.as_completed(futures):
            file_path = futures[future]
            try:
                file_path, strings = future.result()
                for norm_str, positions in strings.items():
                    all_strings[norm_str].append((file_path, positions))
            except Exception as e:
                print(f"Error processing {file_path}: {e}", file=sys.stderr)

    # Filter to keep only repeated strings
    repeated = {k: v for k, v in all_strings.items() if len(v) > 1}

    return repeated


def remove_strings_from_files(
    repeated_strings: Dict[str, List[Tuple[Path, List[Tuple[int, int]]]]], string_numbers: Optional[List[int]] = None
):
    """
    Remove repeated multiline strings from files.

    Args:
        repeated_strings: Dictionary of repeated strings
        string_numbers: List of string numbers to remove (1-based). If None, remove all.
    """
    # Convert repeated_strings dict to ordered list for indexing
    string_list = list(repeated_strings.items())

    # Filter strings to remove based on numbers
    if string_numbers:
        # Convert 1-based numbers to 0-based indices
        indices_to_remove = [n - 1 for n in string_numbers if 1 <= n <= len(string_list)]
        strings_to_remove = {
            norm_str: occurrences for i, (norm_str, occurrences) in enumerate(string_list) if i in indices_to_remove
        }
    else:
        strings_to_remove = repeated_strings

    if not strings_to_remove:
        print("No strings matched the specified numbers.")
        return

    files_to_modify = defaultdict(set)

    # Collect all files and their positions to remove
    for norm_str, occurrences in strings_to_remove.items():
        for file_path, positions in occurrences:
            files_to_modify[file_path].update(positions)

    # Process each file
    for file_path, positions in files_to_modify.items():
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            # Sort positions by start line in reverse to avoid index shifting
            sorted_positions = sorted(positions, key=lambda x: x[0], reverse=True)

            for start, end in sorted_positions:
                # Remove lines from start to end
                del lines[start : end + 1]

            # Write back the modified content
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f"Removed {len(positions)} string(s) from {file_path}")

        except Exception as e:
            print(f"Error modifying {file_path}: {e}", file=sys.stderr)


def save_strings_to_file(repeated_strings: Dict[str, List[Tuple[Path, List[Tuple[int, int]]]]], output_file: Path):
    """Save found repeated strings to a file."""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Repeated Multiline Strings Report\n")
            f.write("=" * 50 + "\n\n")

            for i, (norm_str, occurrences) in enumerate(repeated_strings.items(), 1):
                f.write(f"String #{i} (found {len(occurrences)} times):\n")
                f.write("-" * 30 + "\n")

                # Write the string content
                f.write(norm_str)
                f.write("\n\n")

                # Write locations
                f.write("Found in:\n")
                for file_path, positions in occurrences:
                    f.write(f"  - {file_path}\n")
                    for start, end in positions:
                        f.write(f"    Lines {start + 1}-{end + 1}\n")

                f.write("\n" + "=" * 50 + "\n\n")

        print(f"Report saved to {output_file}")

    except Exception as e:
        print(f"Error saving report: {e}", file=sys.stderr)


def print_summary(repeated_strings: Dict[str, List[Tuple[Path, List[Tuple[int, int]]]]]):
    """Print summary of found repeated strings with numbered index."""
    if not repeated_strings:
        print("No repeated multiline strings found.")
        return

    print(f"\nFound {len(repeated_strings)} repeated multiline strings:")

    for i, (norm_str, occurrences) in enumerate(repeated_strings.items(), 1):
        preview = norm_str[:100] + "..." if len(norm_str) > 100 else norm_str
        preview = preview.replace("\n", "\\n")
        print(f"\n{i}. String #{i} (found in {len(occurrences)} files):")
        print(f"   Preview: {preview}")
        for file_path, positions in occurrences:
            print(f"   - {file_path}")
            for start, end in positions:
                print(f"     Lines {start + 1}-{end + 1}")


def parse_string_numbers(args_strings):
    """Parse string numbers from argument, supporting formats like '2,4' or '2 4' or ['2', '4']"""
    if isinstance(args_strings, str):
        # If it's a single string, try to parse it
        try:
            # Try comma-separated format
            if "," in args_strings:
                return [int(x.strip()) for x in args_strings.split(",")]
            # Try space-separated format
            else:
                return [int(x.strip()) for x in args_strings.split()]
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid string number format: {args_strings}")
    elif isinstance(args_strings, list):
        # If it's already a list
        numbers = []
        for item in args_strings:
            if isinstance(item, str) and "," in item:
                numbers.extend([int(x.strip()) for x in item.split(",")])
            else:
                numbers.append(int(item))
        return numbers
    return []


def main():
    parser = argparse.ArgumentParser(description="Find repeated multiline strings in text files recursively")
    parser.add_argument("directory", nargs="?", default=".", help="Directory to search (default: current directory)")
    parser.add_argument(
        "-r",
        "--remove",
        nargs="*",
        default=None,
        const=[],  # When -r is used without arguments
        help="Remove found repeated strings from files. Optionally specify string numbers to remove (e.g., -r 2 4 or -r 2,4)",
    )
    parser.add_argument("-s", "--save", action="store_true", help="Save found strings to lic.txt in current directory")
    parser.add_argument(
        "--min-lines",
        type=int,
        default=MIN_LINES,
        help=f"Minimum number of lines for a multiline string (default: {MIN_LINES})",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=MIN_CHARS,
        help=f"Minimum number of characters for a multiline string (default: {MIN_CHARS})",
    )
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers (default: CPU count)")
    parser.add_argument("--extensions", nargs="+", help="File extensions to process (e.g., .txt .md .py)")

    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.exists():
        print(f"Directory {directory} does not exist", file=sys.stderr)
        sys.exit(1)

    # Parse extensions
    extensions: Optional[Set[str]] = None
    if args.extensions:
        extensions = set()
        for ext in args.extensions:
            if ext.startswith("."):
                extensions.add(ext)
            else:
                extensions.add(f".{ext}")

    # Find repeated strings
    print(f"Searching for repeated multiline strings in {directory}...")

    repeated = find_repeated_strings(
        directory, min_lines=args.min_lines, min_chars=args.min_chars, max_workers=args.workers, extensions=extensions
    )

    if not repeated:
        print("No repeated multiline strings found.")
        return

    # Print summary
    print_summary(repeated)

    # Handle removal
    if args.remove is not None:  # -r flag was used
        if args.remove == []:  # -r used without specific numbers
            print("\nRemoving ALL repeated strings from files...")
            remove_strings_from_files(repeated)
        else:  # -r used with specific numbers
            # Parse string numbers
            try:
                string_numbers = parse_string_numbers(args.remove)
                if not string_numbers:
                    print("No valid string numbers specified. Use format: -r 2 4 or -r 2,4")
                    return

                print(f"\nRemoving strings with numbers: {string_numbers}")
                remove_strings_from_files(repeated, string_numbers)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return

    # Save to file if requested
    if args.save:
        output_file = Path.cwd() / "lic.txt"
        print(f"\nSaving report to {output_file}...")
        save_strings_to_file(repeated, output_file)


if __name__ == "__main__":
    main()
