#!/usr/bin/env python3
"""
Remove docstrings from Python source files using AST manipulation.
Preserves the module docstring and leaves all comments untouched.

Usage:
    remove_docstrings.py [file_or_directory]

If no argument is given, the current directory is processed recursively.
"""

import ast
import sys
import os
import argparse
from multiprocessing import Pool, cpu_count
from typing import List, Tuple


def get_offset_map(source: str) -> List[int]:
    """
    Pre-calculate start offsets of each line in the source string.
    Returns a list where index i gives the character offset of line i (0-based).
    """
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def offset_from_pos(lineno: int, col_offset: int, line_offsets: List[int]) -> int:
    """
    Convert a 1-based line number and 0-based column offset into a character offset.
    """
    return line_offsets[lineno - 1] + col_offset


def gather_docstring_ranges(tree: ast.AST) -> List[Tuple[int, int]]:
    """
    Walk the AST and collect (start_offset, end_offset) for all docstrings
    that should be removed (i.e. everything except the module docstring).

    We only consider the very first statement of a function/class/async function
    body if it is an expression containing a string constant.
    """
    ranges = []

    # Identify the module docstring so we can skip it.
    module_doc = None
    if (
        isinstance(tree, ast.Module)
        and tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        module_doc = tree.body[0]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.body:
                continue
            first = node.body[0]
            # Check if first statement is a string expression (docstring)
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                # Skip the module-level docstring
                if first is module_doc:
                    continue
                # Record its exact position in the source
                ranges.append((first.lineno, first.col_offset, first.end_lineno, first.end_col_offset))
    return ranges


def remove_ranges_from_source(source: str, ranges: List[Tuple[int, int, int, int]]) -> str:
    """
    Given the original source and a list of (start_lineno, start_col,
    end_lineno, end_col) for the docstrings to remove, delete those spans.
    Ranges are processed from last to first to keep offsets valid.
    """
    if not ranges:
        return source

    line_offsets = get_offset_map(source)

    # Convert line/col to absolute offsets
    abs_ranges = []
    for sl, sc, el, ec in ranges:
        start = offset_from_pos(sl, sc, line_offsets)
        end = offset_from_pos(el, ec, line_offsets)
        abs_ranges.append((start, end))

    # Sort descending so we can delete without affecting earlier positions
    abs_ranges.sort(key=lambda r: r[0], reverse=True)

    # Remove the slices
    for start, end in abs_ranges:
        source = source[:start] + source[end:]

    return source


def process_file(filepath: str) -> str:
    """
    Process a single Python file:
      - parse it
      - identify docstrings (except module docstring)
      - remove them from the source text
      - overwrite the file if changes were made
    Returns a status message.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=filepath)
        ranges = gather_docstring_ranges(tree)

        if not ranges:
            return f"{filepath}: no docstrings to remove"

        new_source = remove_ranges_from_source(source, ranges)

        # Only write if something actually changed
        if new_source != source:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_source)
            return f"{filepath}: removed {len(ranges)} docstring(s)"
        else:
            return f"{filepath}: no changes"
    except SyntaxError as e:
        return f"{filepath}: syntax error - {e}"
    except Exception as e:
        return f"{filepath}: error - {e}"


def find_py_files(root: str) -> List[str]:
    """Recursively collect all .py files under a directory."""
    py_files = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(os.path.join(dirpath, fname))
    return py_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove docstrings from Python files (preserving module docstring).")
    parser.add_argument(
        "path", nargs="?", default=None, help="A Python file or a directory. Defaults to current directory."
    )
    parser.add_argument(
        "--workers", type=int, default=None, help="Number of parallel workers (default: number of CPUs)."
    )
    args = parser.parse_args()

    if args.path is None:
        target = os.getcwd()
    else:
        target = os.path.abspath(args.path)

    # Collect files to process
    if os.path.isfile(target):
        py_files = [target]
    elif os.path.isdir(target):
        py_files = find_py_files(target)
    else:
        print(f"Error: '{target}' is not a valid file or directory.", file=sys.stderr)
        sys.exit(1)

    if not py_files:
        print("No Python files found.")
        return

    workers = args.workers or cpu_count()
    print(f"Processing {len(py_files)} file(s) with {workers} worker(s)...")

    # Use multiprocessing for speed
    with Pool(processes=workers) as pool:
        results = pool.map(process_file, py_files)

    for msg in results:
        print(msg)


if __name__ == "__main__":
    main()
