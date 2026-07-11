#!/data/data/com.termux/files/usr/bin/env python
import argparse
from pathlib import Path
from multiprocessing import Pool, cpu_count
import sys
from typing import List, Generator, Optional


def process_file(file_path: Path) -> None:
    """Process a single file to remove extra blank lines while preserving single blank lines."""
    try:
        # Process the file in a memory-efficient way
        temp_file = file_path.with_suffix(file_path.suffix + ".tmp")

        with (
            file_path.open("r", encoding="utf-8", errors="replace") as infile,
            temp_file.open("w", encoding="utf-8", errors="replace") as outfile,
        ):
            blank_count = 0
            first_line = True

            for line in infile:
                is_blank = not line.strip()

                if not first_line:
                    outfile.write("\n")

                if is_blank:
                    blank_count += 1
                    # Only write first blank line in a sequence
                    if blank_count == 1:
                        outfile.write("\n")
                else:
                    blank_count = 0
                    outfile.write(line.rstrip("\n"))

                first_line = False

            # Special case for files ending with blank lines
            if not first_line and not line.endswith("\n"):
                outfile.write("\n")

        # Replace original file with processed file
        temp_file.replace(file_path)
        print(f"Processed: {file_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}", file=sys.stderr)


def collect_text_files(paths: List[str]) -> Generator[Path, None, None]:
    """Collect all text files from the given paths."""
    text_extensions = {
        ".txt",
        ".md",
        ".py",
        ".html",
        ".css",
        ".js",
        ".json",
        ".xml",
        ".yml",
        ".yaml",
        ".csv",
        ".ini",
        ".conf",
        ".log",
    }

    def is_text_file(file_path: Path) -> bool:
        """Check if a file is likely a text file based on extension."""
        return file_path.suffix.lower() in text_extensions

    for path in paths:
        p = Path(path)
        if p.is_file() and is_text_file(p):
            yield p.resolve()
        elif p.is_dir():
            yield from (f.resolve() for f in p.rglob("*") if f.is_file() and is_text_file(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove extra blank lines from text files recursively.")
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        default=["."],
        help="Files or directories to process (default: current directory)",
    )
    args = parser.parse_args()

    # Collect all text files
    files = list(collect_text_files(args.paths))

    if not files:
        print("No text files found to process.", file=sys.stderr)
        return

    print(f"Found {len(files)} text file(s) to process.", file=sys.stderr)

    # Use multiprocessing with number of available CPUs
    num_processes = max(1, cpu_count())

    # Process files in parallel
    with Pool(processes=num_processes) as pool:
        results = pool.imap_unordered(process_file, files)
        for _ in results:
            pass  # Just iterate through results to catch any exceptions


if __name__ == "__main__":
    main()
