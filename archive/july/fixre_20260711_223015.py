#!/data/data/com.termux/files/usr/bin/env python

"""
Convert escaped regex strings back to raw string format.
Handles all re module functions (compile, sub, findall, match, search, etc.).
Processes Python files with optimized single-threaded or parallel processing.
"""

import ast
import sys
import shutil
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import Optional, Tuple, List, Set
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import os

# All re functions that accept regex patterns as first argument
RE_FUNCTIONS = {"compile", "search", "match", "fullmatch", "split", "findall", "finditer", "sub", "subn"}

# Common regex escape sequences that indicate a raw string is needed
REGEX_INDICATORS = {
    r"\d",
    r"\w",
    r"\s",
    r"\S",
    r"\W",
    r"\D",
    r"[",
    r"]",
    r"(",
    r")",
    r"|",
    r"^",
    r"$",
    r"+",
    r"*",
    r"?",
    r"{",
    r"}",
    r".",
    r"\b",
    r"\B",
    r"\A",
    r"\Z",
    r"\z",
    r"\1",
    r"\2",
    r"\3",
    r"\4",
    r"\5",
    r"\6",
    r"\7",
    r"\8",
    r"\9",
}

# Python string escape sequences that need special handling
STRING_ESCAPES = {"\\n", "\\t", "\\r", "\\f", "\\v", "\\\\", "\\'", '\\"', "\\a", "\\b"}


@dataclass
class StringInfo:
    """Information about a string literal in the AST"""

    value: str
    lineno: int
    col_offset: int
    end_col: int
    is_raw: bool = False
    is_fstring: bool = False
    quote_char: str = '"'


def needs_raw_string(string_content: str) -> bool:
    """Determine if a string should be converted to raw format"""
    if not string_content:
        return False

    # Check for regex patterns
    has_regex_pattern = any(indicator in string_content for indicator in REGEX_INDICATORS)

    # Check for escape sequences
    escape_count = 0
    i = 0
    while i < len(string_content) - 1:
        if string_content[i] == "\\":
            if string_content[i + 1] in "\\abfnrtv\"'":  # Valid Python escapes
                escape_count += 1
                if escape_count >= 2 or (escape_count >= 1 and has_regex_pattern):
                    return True
            i += 1
        i += 1

    return False


def extract_and_convert_strings(content: str) -> Optional[str]:
    """Extract and convert regex string arguments in re function calls"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    # Collect string positions that need conversion
    conversions = []

    class RegexStringVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # Check if this is an re function call
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"
                and node.func.attr in RE_FUNCTIONS
                and node.args
            ):
                # Check the first argument
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    # Check if it's a raw string already
                    is_raw = False
                    is_fstring = False

                    # Get the actual source representation
                    # We need to look at the source to determine if it's already raw
                    if hasattr(arg, "lineno") and hasattr(arg, "col_offset"):
                        # Store for conversion check
                        string_val = arg.value
                        if needs_raw_string(string_val):
                            conversions.append({
                                "lineno": arg.lineno,
                                "col_offset": arg.col_offset,
                                "end_col": arg.end_col_offset,
                                "value": string_val,
                                "is_raw": is_raw,
                                "is_fstring": is_fstring,
                            })

            self.generic_visit(node)

    visitor = RegexStringVisitor()
    visitor.visit(tree)

    if not conversions:
        return None

    # Process the file line by line
    lines = content.split("\n")
    converted = False

    # Sort conversions by line and column in reverse order to maintain positions
    conversions.sort(key=lambda x: (x["lineno"], -x["col_offset"]))

    for conv in conversions:
        line_idx = conv["lineno"] - 1
        if line_idx >= len(lines):
            continue

        line = lines[line_idx]
        col_start = conv["col_offset"]
        col_end = conv["end_col"]

        # Extract the original string literal
        original_literal = line[col_start:col_end]

        # Skip if it's already a raw string
        if original_literal.startswith(('r"', "r'", 'r"""', "r'''")):
            continue

        # Skip multi-line strings
        if original_literal.startswith(('"""', "'''")):
            continue

        # Determine quote character
        quote_char = original_literal[0] if original_literal else '"'
        if quote_char not in ['"', "'"]:
            continue

        # Create the raw string literal
        escaped_value = conv["value"]
        new_literal = f"r{quote_char}{escaped_value}{quote_char}"

        # Replace in the line
        new_line = line[:col_start] + new_literal + line[col_end:]
        lines[line_idx] = new_line
        converted = True

    if not converted:
        return None

    return "\n".join(lines)


def validate_python_file(content: str) -> bool:
    """Validate that the content is valid Python code"""
    try:
        ast.parse(content)
        return True
    except SyntaxError:
        return False


def process_file(filepath: Path, create_backup: bool = True) -> Tuple[Path, bool, str]:
    """Process a single Python file"""
    try:
        original_content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return (filepath, False, f"Failed to read: {e}")

    # Skip if no re imports or function calls are present (quick check)
    if "re." not in original_content:
        return (filepath, True, "No re calls found")

    # Convert strings
    converted_content = extract_and_convert_strings(original_content)
    if converted_content is None:
        return (filepath, True, "No changes needed")

    # Validate the converted content
    if not validate_python_file(converted_content):
        return (filepath, False, "Validation failed - syntax error after conversion")

    try:
        # Create backup
        if create_backup:
            backup_path = filepath.with_suffix(filepath.suffix + ".backup")
            shutil.copy2(filepath, backup_path)

        # Write the converted content
        filepath.write_text(converted_content, encoding="utf-8")
        return (filepath, True, "✓ Converted and saved")
    except Exception as e:
        return (filepath, False, f"Failed to write: {e}")


def collect_python_files(inputs: List[Path]) -> List[Path]:
    """Collect all Python files from the given paths"""
    python_files = set()
    for input_path in inputs:
        if not input_path.exists():
            print(f"Warning: Path does not exist: {input_path}", file=sys.stderr)
            continue

        if input_path.is_file():
            if input_path.suffix == ".py":
                python_files.add(input_path)
        elif input_path.is_dir():
            # Skip virtual environments and cache directories
            skip_dirs = {".venv", "venv", "env", "__pycache__", ".git", "node_modules"}
            for py_file in input_path.rglob("*.py"):
                # Skip files in excluded directories
                if any(part in skip_dirs for part in py_file.parts):
                    continue
                python_files.add(py_file)

    return sorted(python_files)


def parse_arguments():
    """Parse command line arguments"""
    args = sys.argv[1:]

    if not args:
        return [], True  # Use current directory, create backups

    # Check for --no-backup flag
    create_backup = True
    if "--no-backup" in args:
        create_backup = False
        args.remove("--no-backup")

    # Check for --workers flag
    num_workers = min(cpu_count(), 4)  # Default to 4 or CPU count
    for i, arg in enumerate(args):
        if arg == "--workers" and i + 1 < len(args):
            try:
                num_workers = int(args[i + 1])
                args.pop(i)
                args.pop(i)
            except ValueError:
                pass
            break

    paths = [Path(arg).resolve() for arg in args] if args else [Path.cwd()]

    return paths, create_backup, num_workers


def main():
    """Main entry point"""
    # Parse arguments
    paths, create_backup, num_workers = parse_arguments()

    # Collect Python files
    python_files = collect_python_files(paths)

    if not python_files:
        print("No Python files found")
        return

    print(f"Found {len(python_files)} Python files")
    print(f"Processing with {num_workers} workers")
    print(f"Backup: {'Enabled' if create_backup else 'Disabled'}")
    print(f"Target re functions: {', '.join(sorted(RE_FUNCTIONS))}\n")

    # Process files in parallel
    results = []
    total = len(python_files)

    if num_workers > 1:
        with Pool(processes=num_workers) as pool:
            # Use starmap to pass additional arguments
            results = pool.starmap(process_file, [(f, create_backup) for f in python_files])
    else:
        # Single-threaded processing for better debugging
        for i, filepath in enumerate(python_files, 1):
            if i % 100 == 0:
                print(f"Progress: {i}/{total}", flush=True)
            results.append(process_file(filepath, create_backup))

    # Print summary
    successful = sum(1 for _, success, _ in results if success)
    changed = sum(1 for _, success, msg in results if success and "Converted" in msg)

    print("\n" + "=" * 70)
    for filepath, success, message in results:
        status = "✓" if success else "✗"
        try:
            rel_path = filepath.relative_to(Path.cwd())
        except ValueError:
            rel_path = filepath
        print(f"{status} {rel_path}: {message}")
    print("=" * 70)

    print(f"\nSummary:")
    print(f"  Total files: {len(python_files)}")
    print(f"  Processed successfully: {successful}")
    print(f"  Files converted: {changed}")

    if not create_backup:
        print("\n⚠️  Backup disabled. Use --no-backup with caution.")


if __name__ == "__main__":
    main()
