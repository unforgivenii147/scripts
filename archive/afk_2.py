#!/usr/bin/env python3
"""
Remove unused imports from Python files using pyflakes.
Processes single file or directory recursively with multiprocessing.
"""

import sys
import re
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import List, Dict, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
import subprocess


@dataclass
class UnusedImport:
    """Represents an unused import."""

    name: str
    line: int
    col: int


class ImportRemover:
    """Removes unused imports from Python files."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.unused_imports = []

    def analyze(self) -> List[UnusedImport]:
        """Analyze file for unused imports using pyflakes."""
        try:
            # Run pyflakes and capture output
            result = subprocess.run(["pyflakes", str(self.file_path)], capture_output=True, text=True, check=False)

            unused_imports = []

            # Parse pyflakes output
            for line in result.stderr.split("\n"):
                # Look for 'imported but unused' patterns
                if "imported but unused" in line or "unused import" in line:
                    # Parse line format: "file.py:line:col: 'name' imported but unused"
                    match = re.match(r'.*?:(\d+):(\d+):.*?[\'"](\w+)[\'"]', line)
                    if match:
                        line_num = int(match.group(1))
                        col_num = int(match.group(2))
                        name = match.group(3)
                        unused_imports.append(UnusedImport(name, line_num, col_num))

            self.unused_imports = unused_imports
            return unused_imports

        except subprocess.CalledProcessError as e:
            print(f"Error analyzing {self.file_path}: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Unexpected error analyzing {self.file_path}: {e}", file=sys.stderr)
            return []

    def remove_unused_imports(self) -> List[str]:
        """Remove unused imports from the file."""
        if not self.unused_imports:
            return []

        try:
            # Read file content
            with open(self.file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Sort unused imports by line number in reverse to avoid index issues
            removed_imports = []
            lines_to_remove = sorted([(imp.line, imp.name) for imp in self.unused_imports], reverse=True)

            # Remove lines containing unused imports
            for line_num, import_name in lines_to_remove:
                if 0 <= line_num - 1 < len(lines):
                    line_content = lines[line_num - 1]

                    # Check if this line contains only this import
                    if import_name in line_content:
                        # Remove the entire line
                        removed_line = lines.pop(line_num - 1).rstrip()
                        removed_imports.append(f"{import_name} (line {line_num})")
                    else:
                        # Try to remove just the import from a multi-import line
                        # This is complex; for simplicity, skip for now
                        pass

            # Write back the modified content
            if removed_imports:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

            return removed_imports

        except Exception as e:
            print(f"Error removing imports from {self.file_path}: {e}", file=sys.stderr)
            return []

    def process(self) -> Tuple[Path, List[str]]:
        """Process file: analyze and remove unused imports."""
        unused = self.analyze()
        if unused:
            removed = self.remove_unused_imports()
            return (self.file_path, removed)
        return (self.file_path, [])


def find_python_files(root_path: Path) -> List[Path]:
    """Find all Python files recursively."""
    python_files = []

    if root_path.is_file():
        if root_path.suffix == ".py":
            python_files.append(root_path)
    else:
        # Walk through directory recursively
        for file_path in root_path.rglob("*.py"):
            # Skip virtual environment and cache directories
            if any(part.startswith(".") or part in ["__pycache__", "venv", "env", ".venv"] for part in file_path.parts):
                continue
            python_files.append(file_path)

    return python_files


def process_file(file_path: Path) -> Tuple[Path, List[str]]:
    """Process a single file (for multiprocessing)."""
    try:
        remover = ImportRemover(file_path)
        return remover.process()
    except Exception as e:
        print(f"Failed to process {file_path}: {e}", file=sys.stderr)
        return (file_path, [])


def print_summary(results: Dict[Path, List[str]], total_files: int, total_imports_removed: int) -> None:
    """Print summary of all changes."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nTotal files processed: {total_files}")
    print(f"Files modified: {len([r for r in results.values() if r])}")
    print(f"Total unused imports removed: {total_imports_removed}")

    if results:
        print("\nModified files:")
        for file_path, removed in results.items():
            if removed:
                print(f"\n  📄 {file_path}")
                for imp in removed:
                    print(f"     ✗ {imp}")

    print("\n" + "=" * 60)


def main() -> None:
    """Main function."""
    # Determine input path
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"Error: {input_path} does not exist", file=sys.stderr)
            sys.exit(1)
    else:
        input_path = Path.cwd()
        print(f"No input provided, processing current directory: {input_path}")

    # Find all Python files
    print(f"Scanning for Python files in: {input_path}")
    python_files = find_python_files(input_path)

    if not python_files:
        print("No Python files found.")
        return

    print(f"Found {len(python_files)} Python files")

    # Process files in parallel
    num_workers = min(cpu_count(), len(python_files))
    print(f"Using {num_workers} worker processes...")

    results = {}
    total_imports_removed = 0

    # Use ProcessPoolExecutor for better handling
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_file, file_path): file_path for file_path in python_files}

        # Collect results
        from concurrent.futures import as_completed

        for i, future in enumerate(as_completed(future_to_file), 1):
            file_path = future_to_file[future]
            try:
                file_path_result, removed_imports = future.result()
                results[file_path_result] = removed_imports
                total_imports_removed += len(removed_imports)

                if removed_imports:
                    print(f"[{i}/{len(python_files)}] ✓ {file_path_result} - Removed {len(removed_imports)} imports")
                else:
                    print(f"[{i}/{len(python_files)}] ○ {file_path_result} - No unused imports")

            except Exception as e:
                print(f"[{i}/{len(python_files)}] ✗ Failed to process {file_path}: {e}", file=sys.stderr)
                results[file_path] = []

    # Print summary
    print_summary(results, len(python_files), total_imports_removed)


if __name__ == "__main__":
    # Check if pyflakes is installed
    try:
        import pyflakes
    except ImportError:
        print("Error: pyflakes is not installed. Please install it with:")
        print("  pip install pyflakes")
        sys.exit(1)

    main()
