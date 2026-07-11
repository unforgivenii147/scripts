#!/data/data/com.termux/files/usr/bin/python

"""
Remove comments from Python files recursively while preserving:
- Shebang lines (#!)
- Type comments (# type:)
- Format comments (# fmt:)
Supports inline comments, validates with AST before writing.
"""

import ast
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Tuple

from dh import get_pyfiles


class CommentRemover:
    """Remove comments from Python code while preserving special comments."""

    def __init__(self) -> None:
        # Patterns for comments to preserve (full line or inline)
        self.preserve_patterns = [
            r"^#!",  # Shebang
            r"#\s*type:",  # Type comments (inline supported)
            r"#\s*fmt:",  # Format comments (inline supported)
            r"#\s*pragma:",  # Pragma comments
            r"#\s*noqa",  # Flake8 noqa (inline supported)
            r"#\s*pylint:",  # Pylint comments (inline supported)
            r"#\s*flake8:",  # Flake8 comments (inline supported)
            r"#\s*mypy:",  # Mypy comments (inline supported)
        ]

        # Compile patterns for efficiency
        self.preserve_regex = re.compile("|".join(self.preserve_patterns))

    def remove_comments(self, content: str) -> Tuple[str, int]:
        """
        Remove comments from Python code while preserving special comments.
        Supports inline comments.

        Returns:
            Tuple of (modified_content, removed_count)
        """
        lines = content.splitlines(keepends=True)
        modified_lines = []
        removed_count = 0
        in_string = False
        string_char = None
        escape_next = False

        for line in lines:
            # Process line character by character to handle strings and inline comments
            new_line_chars = []
            i = 0
            comment_start = -1
            in_comment = False

            while i < len(line):
                char = line[i]

                # Handle escape sequences
                if escape_next:
                    if not in_comment:
                        new_line_chars.append(char)
                    escape_next = False
                    i += 1
                    continue

                if char == "\\":
                    escape_next = True
                    if not in_comment:
                        new_line_chars.append(char)
                    i += 1
                    continue

                # Toggle string state (only if not in comment)
                if not in_comment and char in ('"', "'"):
                    if not in_string:
                        in_string = True
                        string_char = char
                        new_line_chars.append(char)
                    elif string_char == char:
                        in_string = False
                        string_char = None
                        new_line_chars.append(char)
                    else:
                        new_line_chars.append(char)
                    i += 1
                    continue

                # Check for comment start (not in string)
                if not in_string and char == "#" and not in_comment:
                    # Check if this is a preserved comment
                    remaining_line = line[i:]
                    is_preserved = False

                    for pattern in self.preserve_patterns:
                        if re.search(pattern, remaining_line):
                            is_preserved = True
                            break

                    if is_preserved:
                        # Keep the preserved comment and rest of line
                        new_line_chars.extend(line[i:])
                        break
                    else:
                        # This is a regular comment to remove
                        in_comment = True
                        comment_start = i
                        # Remove trailing whitespace before comment
                        while new_line_chars and new_line_chars[-1] in (" ", "\t"):
                            new_line_chars.pop()
                        i += 1
                        continue

                # Add character if not in comment
                if not in_comment:
                    new_line_chars.append(char)

                i += 1

            # Handle line ending
            if not in_comment and comment_start == -1:
                # No comment removed, keep line as is
                modified_lines.append("".join(new_line_chars))
            else:
                # Comment was removed
                if new_line_chars and new_line_chars[-1] == "\n":
                    modified_lines.append("".join(new_line_chars))
                else:
                    # Ensure line ending is preserved
                    result_line = "".join(new_line_chars)
                    if line.endswith("\n") and not result_line.endswith("\n"):
                        result_line += "\n"
                    modified_lines.append(result_line)
                if in_comment:
                    removed_count += 1

            # Reset string state for next line (strings don't span lines in Python with implicit concat)
            # But we need to handle triple-quoted strings properly
            if in_string and string_char:
                # For simplicity, assume strings don't cross lines unless triple-quoted
                # This is a simplification - a full parser would be better
                pass

        return "".join(modified_lines), removed_count


def validate_python_syntax(content: str) -> Tuple[bool, str]:
    """
    Validate Python syntax using ast.parse.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def process_file(file_path: Path) -> Tuple[Path, bool, int, float, bool]:
    """
    Process a single Python file to remove comments.

    Returns:
        Tuple of (file_path, was_modified, removed_count, elapsed_ms, syntax_valid)
    """
    start_time = time.perf_counter()

    try:
        # Read file content
        original_content = file_path.read_text(encoding="utf-8")

        # Remove comments
        remover = CommentRemover()
        modified_content, removed_count = remover.remove_comments(original_content)

        # Validate syntax if changes were made
        was_modified = False
        syntax_valid = True

        if modified_content != original_content and removed_count > 0:
            # Check if modified code has valid syntax
            is_valid, error_msg = validate_python_syntax(modified_content)

            if is_valid:
                # Write back to file
                file_path.write_text(modified_content, encoding="utf-8")
                was_modified = True
                syntax_valid = True
            else:
                # Syntax error detected, skip writing
                syntax_valid = False
                was_modified = False
                print(f"  ⚠ Warning: {file_path} would have syntax error, skipping write: {error_msg}", file=sys.stderr)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return file_path, was_modified, removed_count, elapsed_ms, syntax_valid

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return file_path, False, 0, elapsed_ms, False


def find_python_files(directory: Path) -> list:
    """Recursively find all Python files in directory."""
    return list(directory.rglob("*.py"))


def format_report(file_path: Path, was_modified: bool, count: int, elapsed_ms: float, syntax_valid: bool) -> str:
    """Format report line for a file."""
    if not syntax_valid:
        return f"{file_path} {elapsed_ms:.0f}ms (SKIPPED - syntax error)"
    elif was_modified:
        status = f"{count} comment{'s' if count != 1 else ''} removed"
        return f"{file_path} {elapsed_ms:.0f}ms ({status})"
    else:
        return f"{file_path} {elapsed_ms:.0f}ms (no change)"


def main() -> None:
    cwd = Path.cwd()

    # Find all Python files
    python_files = get_pyfiles(cwd)

    if not python_files:
        print("No Python files found.")
        return

    print(f"Found {len(python_files)} Python file(s) to process\n")

    # Process files concurrently
    results = []
    total_start = time.perf_counter()

    with ProcessPoolExecutor(max_workers=4) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_file, file_path): file_path for file_path in python_files}

        # Collect results as they complete
        for future in as_completed(future_to_file):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                file_path = future_to_file[future]
                print(f"Error processing {file_path}: {e}", file=sys.stderr)

    total_elapsed = (time.perf_counter() - total_start) * 1000

    # Sort results by file path for consistent output
    results.sort(key=lambda x: str(x[0]))

    # Print report
    total_removed = 0
    total_modified = 0
    total_skipped = 0

    for file_path, was_modified, count, elapsed_ms, syntax_valid in results:
        print(format_report(file_path, was_modified, count, elapsed_ms, syntax_valid))
        if was_modified:
            total_removed += count
            total_modified += 1
        elif not syntax_valid and count > 0:
            total_skipped += 1

    # Print summary
    print("-" * 80)
    print(f"Summary: {total_modified} file(s) modified, {total_removed} comment(s) removed")
    if total_skipped > 0:
        print(f"  ⚠ {total_skipped} file(s) skipped due to syntax errors")
    print(f"Total time: {total_elapsed:.0f}ms")


if __name__ == "__main__":
    main()
