#!/data/data/com.termux/files/usr/bin/env python
"""
Insert SKIP_DIRS definition after import section in Python files.
Uses parallel processing for better performance.
"""

import ast
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple


INSERT_TEXT = (
    '\nSKIP_DIRS = frozenset({"lazy", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"})\n'
)


def find_import_section_end(content: str) -> Optional[int]:
    """
    Find the position after the last import statement.
    Uses AST for precise parsing, falls back to regex.
    """
    # Try AST parsing first
    try:
        tree = ast.parse(content)
        last_import_line = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if node.end_lineno and node.end_lineno > last_import_line:
                    last_import_line = node.end_lineno

        if last_import_line > 0:
            # Convert line number to string position
            lines = content.splitlines(True)
            pos = sum(len(line) for line in lines[:last_import_line])
            return pos
    except SyntaxError:
        pass

    # Fallback: regex-based approach
    import_pattern = re.compile(r"^(?:from\s+\S+\s+import\s+.*|import\s+.*)$", re.MULTILINE)

    matches = list(import_pattern.finditer(content))
    if matches:
        last_match = matches[-1]
        return last_match.end()

    return None


def process_file(file_path: Path) -> Tuple[Path, bool]:
    """
    Process a single Python file.
    Returns (file_path, was_modified).
    """
    try:
        # Read file content
        content = file_path.read_text(encoding="utf-8")

        # Check if SKIP_DIRS already exists
        if "SKIP_DIRS" in content:
            return file_path, False

        # Find where to insert
        insert_pos = find_import_section_end(content)

        if insert_pos is None:
            # No imports found, try after shebang and encoding declarations
            lines = content.splitlines(True)
            start_pos = 0

            # Skip shebang
            if lines and lines[0].startswith("#!"):
                start_pos += len(lines[0])
                # Skip encoding declaration
                if len(lines) > 1 and "coding" in lines[1]:
                    start_pos += len(lines[1])

            # Check if there's a docstring at module level
            if start_pos < len(content):
                remaining = content[start_pos:].lstrip()
                if remaining.startswith('"""') or remaining.startswith("'''"):
                    docstring_end = _find_docstring_end(remaining)
                    if docstring_end:
                        start_pos += len(content[start_pos:]) - len(remaining) + docstring_end

            insert_pos = start_pos

        # Ensure proper newline separation
        if insert_pos > 0 and not content[insert_pos - 1 : insert_pos] in ("\n", "\r"):
            insert_text = "\n" + INSERT_TEXT
        else:
            insert_text = INSERT_TEXT

        # Create modified content
        modified_content = content[:insert_pos] + insert_text + content[insert_pos:]

        # Write back to file
        file_path.write_text(modified_content, encoding="utf-8")

        return file_path, True

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return file_path, False


def _find_docstring_end(text: str) -> Optional[int]:
    """Find the end position of a triple-quoted string."""
    for quote in ('"""', "'''"):
        if text.startswith(quote):
            idx = text.find(quote, 3)
            if idx != -1:
                return idx + 3
    return None


def find_python_files(root_dir: Path = Path(".")) -> list[Path]:
    """Find all Python files, respecting SKIP_DIRS."""
    python_files = []

    for py_file in root_dir.rglob("*.py"):
        # Check if any parent directory should be skipped
        parts = set(py_file.parent.parts)
        if parts & SKIP_DIRS:
            continue
        python_files.append(py_file)

    return python_files


def main():
    """Main function to process all Python files."""
    root_dir = Path(".")

    # Find all Python files
    print("Finding Python files...")
    python_files = find_python_files(root_dir)
    print(f"Found {len(python_files)} Python files")

    if not python_files:
        print("No Python files to process")
        return

    # Process files in parallel
    modified_count = 0
    skipped_count = 0
    error_count = 0

    print(f"Processing files using {min(len(python_files), 8)} workers...")

    with ProcessPoolExecutor(max_workers=min(len(python_files), 8)) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_file, file_path): file_path for file_path in python_files}

        # Process results as they complete
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                path, was_modified = future.result()
                if was_modified:
                    modified_count += 1
                    print(f"✓ Modified: {path}")
                else:
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                print(f"✗ Error processing {file_path}: {e}")

    # Print summary
    print(f"\n{'=' * 50}")
    print(f"Summary:")
    print(f"  Total files found: {len(python_files)}")
    print(f"  Modified: {modified_count}")
    print(f"  Skipped (already has SKIP_DIRS): {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
