#!/data/data/com.termux/files/usr/bin/python

"""
Remove unused imports from Python files while preserving all other content.
Uses direct source code scanning (ignoring comments and strings) for high accuracy.
Supports single files, directories (recursive), and multiprocessing.
"""

import re
import sys
from dataclasses import dataclass
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FileResult:
    """Result of processing a single file."""

    path: str
    removed_imports: List[str]
    modified: bool
    error: Optional[str] = None


class ImportCleaner:
    """Remove unused imports by scanning actual usage outside comments/strings."""

    # Imports that are always considered "used" (special cases)
    ALWAYS_KEEP = {
        ("__future__", "annotations"),
        ("__future__", "print_function"),
        ("__future__", "unicode_literals"),
        ("__future__", "absolute_import"),
        ("__future__", "division"),
        ("__future__", "generators"),
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def find_python_files(self, paths: List[str], recursive: bool = True) -> List[Path]:
        """Find all Python files from given paths."""
        python_files = []
        for path_str in paths:
            path = Path(path_str)
            if path.is_file():
                if path.suffix == ".py":
                    python_files.append(path)
                elif self.verbose:
                    print(f"Skipping non-Python file: {path}")
            elif path.is_dir():
                if recursive:
                    python_files.extend(path.rglob("*.py"))
                else:
                    python_files.extend(path.glob("*.py"))
            else:
                print(f"Path does not exist: {path}", file=sys.stderr)
        return python_files

    def remove_comments_and_strings(self, source: str) -> str:
        """Remove comments and string literals from source code to avoid false positives."""
        # Simple but effective: remove triple-quoted strings first, then single-line comments
        # This is not perfect but works for the purpose of finding identifiers.

        # Remove triple-quoted strings (both """ and ''')
        def remove_triple_quotes(text, quote_char):
            pattern = re.compile(
                f"{quote_char}{quote_char}{quote_char}.*?{quote_char}{quote_char}{quote_char}", re.DOTALL
            )
            return pattern.sub(" ", text)

        source = remove_triple_quotes(source, '"')
        source = remove_triple_quotes(source, "'")

        # Remove single-line strings
        # Simple regex: match strings that are not part of comments (we'll handle comments next)
        source = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', " ", source)
        source = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", " ", source)

        # Remove comments (from # to end of line)
        lines = []
        for line in source.split("\n"):
            # Find first # not inside quotes (but quotes already removed)
            hash_pos = line.find("#")
            if hash_pos >= 0:
                line = line[:hash_pos]
            lines.append(line)
        source = "\n".join(lines)

        return source

    def extract_imports(self, source_lines: List[str]) -> Dict[int, Dict]:
        """
        Extract all import statements with their line numbers and the names they define.
        Returns dict: line_number -> {'type': 'import'/'from', 'names': set of defined names, 'original_line': str}
        """
        imports = {}

        # Regex patterns
        import_pattern = re.compile(r"^\s*import\s+(.+?)(?:\s*#.*)?$")
        from_import_pattern = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+(.+?)(?:\s*#.*)?$")

        for i, line in enumerate(source_lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Match simple import: import a, b as c, d.e
            m = import_pattern.match(line)
            if m:
                imports_line = m.group(1)
                names = set()
                # Split by comma, handle 'as'
                for part in imports_line.split(","):
                    part = part.strip()
                    if " as " in part:
                        # import module as alias
                        original, alias = part.split(" as ")
                        names.add(alias.strip())
                    else:
                        # import module (take the first part before dot)
                        # For 'import lz4.frame', the name 'lz4' is what gets used
                        base_name = part.split(".")[0]
                        names.add(base_name)
                if names:
                    imports[i] = {"type": "import", "names": names, "line": line.rstrip("\n"), "module": None}
                continue

            # Match from ... import ...
            m = from_import_pattern.match(line)
            if m:
                module = m.group(1)
                imports_part = m.group(2)
                names = set()
                for part in imports_part.split(","):
                    part = part.strip()
                    if part == "*":
                        # Cannot safely remove star imports
                        names.add("*")
                    elif " as " in part:
                        original, alias = part.split(" as ")
                        names.add(alias.strip())
                    else:
                        names.add(part.strip())
                if names and "*" not in names:  # Skip star imports
                    imports[i] = {"type": "from", "names": names, "line": line.rstrip("\n"), "module": module}

        return imports

    def get_all_used_names(self, source_clean: str) -> Set[str]:
        """
        Extract all identifiers used in the code (after removing comments/strings).
        """
        # Find all words that look like identifiers (letters, numbers, underscore, not starting with digit)
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", source_clean)
        return set(words)

    def import_is_used(self, import_info: Dict, used_names: Set[str], source_lines: List[str]) -> bool:
        """
        Determine if an import is actually used in the file.
        Handles module prefixes (e.g., 'lz4.frame' usage as 'lz4').
        """
        # Always keep __future__ imports
        if import_info["type"] == "from" and import_info.get("module") == "__future__":
            return True

        names = import_info["names"]

        # For 'from module import name', the name is directly used
        if import_info["type"] == "from":
            for name in names:
                if name in used_names:
                    return True
            # Also check if the module itself is used as a prefix? Not typical for 'from'
            return False

        # For 'import module' or 'import module as alias'
        # The name could be the alias or the base module (e.g., 'import lz4.frame' -> 'lz4' is used)
        for name in names:
            if name in used_names:
                return True
            # Also check for dotted usage: if name is 'lz4', check for 'lz4.' in source
            # We need to look for patterns like 'lz4.frame' or 'lz4.something'
            # To avoid re-scanning the whole file multiple times, we'll do a quick check.
            # But used_names already contains 'lz4' if it appears, so this might be enough.
            # However, if the code uses 'lz4.frame.compress()', the token 'lz4' is present.
            # So the above check should catch it.

        # Special case: 'import io' might be used via 'io.' - 'io' will appear as a name
        return False

    def clean_file(self, file_path: Path, in_place: bool = False) -> FileResult:
        """Clean unused imports from a single file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_lines = f.readlines()

            if not any(l.strip() for l in original_lines):
                return FileResult(str(file_path), [], False)

            source = "".join(original_lines)

            # Clean version for scanning (remove comments/strings)
            clean_source = self.remove_comments_and_strings(source)
            used_names = self.get_all_used_names(clean_source)

            # Extract all imports
            imports = self.extract_imports(original_lines)

            # Find unused imports
            lines_to_remove = set()
            removed_list = []

            for line_num, imp_info in imports.items():
                if not self.import_is_used(imp_info, used_names, original_lines):
                    lines_to_remove.add(line_num)
                    removed_list.append(imp_info["line"].strip())

            if not removed_list:
                if self.verbose:
                    print(f"✓ No unused imports: {file_path}")
                return FileResult(str(file_path), [], False)

            # Rebuild file without those lines
            cleaned_lines = [line for i, line in enumerate(original_lines, 1) if i not in lines_to_remove]
            cleaned_content = "".join(cleaned_lines)

            # Write output
            if in_place:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_content)
                if self.verbose:
                    print(f"✓ Updated: {file_path}")
            else:
                output_path = file_path.parent / f"{file_path.stem}_cleaned{file_path.suffix}"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_content)
                if self.verbose:
                    print(f"✓ Created: {output_path}")

            return FileResult(str(file_path), removed_list, True)

        except Exception as e:
            error_msg = f"Error processing {file_path}: {str(e)}"
            if self.verbose:
                print(f"✗ {error_msg}", file=sys.stderr)
            return FileResult(str(file_path), [], False, error_msg)

    def process_file_wrapper(self, args: Tuple[str, bool]) -> FileResult:
        return self.clean_file(Path(args[0]), args[1])


def print_summary(results: List[FileResult], verbose: bool = False):
    """Print a summary of all processed files."""
    total = len(results)
    modified = [r for r in results if r.modified]
    errors = [r for r in results if r.error]

    print("\n" + "=" * 70)
    print("IMPORT CLEANUP SUMMARY")
    print("=" * 70)
    print(f"Total files processed: {total}")
    print(f"Files modified: {len(modified)}")
    print(f"Errors: {len(errors)}")

    if modified:
        total_removed = sum(len(r.removed_imports) for r in modified)
        print(f"Total unused imports removed: {total_removed}")

        print("\n" + "-" * 70)
        print("MODIFIED FILES:")
        print("-" * 70)

        for result in modified:
            print(f"\n📄 {result.path}")
            print(f"   Removed {len(result.removed_imports)} import(s):")
            for imp in result.removed_imports[:15]:
                print(f"     - {imp}")
            if len(result.removed_imports) > 15:
                print(f"     ... and {len(result.removed_imports) - 15} more")

    if errors and verbose:
        print("\n" + "-" * 70)
        print("ERRORS:")
        print("-" * 70)
        for result in errors:
            print(f"   ❌ {result.error}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Remove unused imports from Python files (accurate text scanning)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s script.py                    # Clean single file
  %(prog)s src/                         # Clean directory (recursive)
  %(prog)s src/ --no-recursive          # Clean directory (non-recursive)
  %(prog)s . -i -v                      # Clean current directory in place with verbose
  %(prog)s file1.py file2.py --no-mp    # Process multiple files sequentially
  %(prog)s src/ tests/ -i               # Clean multiple directories in place

Note: __future__ imports are always preserved. Imports used inside conditional blocks or
      via module prefixes (e.g., 'import lz4.frame' used as 'lz4.frame.compress()') are detected.
        """,
    )

    parser.add_argument("paths", nargs="+", help="Files or directories to process")
    parser.add_argument(
        "--in-place", "-i", action="store_true", help="Modify files in place (creates _cleaned copies by default)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--recursive", "-r", action="store_true", default=True, help="Process directories recursively (default: True)"
    )
    parser.add_argument("--no-recursive", action="store_true", help="Do not process directories recursively")
    parser.add_argument("--no-mp", action="store_true", help="Disable multiprocessing")

    args = parser.parse_args()

    recursive = args.recursive and not args.no_recursive

    cleaner = ImportCleaner(verbose=args.verbose)
    python_files = cleaner.find_python_files(args.paths, recursive)

    if not python_files:
        print("No Python files found to process.")
        return

    if args.verbose:
        print(f"Found {len(python_files)} Python file(s) to process")
        if args.no_mp:
            print("Processing sequentially...")
        else:
            print(f"Processing with {cpu_count()} CPU cores...")

    if args.no_mp or len(python_files) < 2:
        results = []
        for file_path in python_files:
            results.append(cleaner.clean_file(file_path, args.in_place))
    else:
        with Pool(processes=cpu_count()) as pool:
            tasks = [(str(fp), args.in_place) for fp in python_files]
            results = pool.map(cleaner.process_file_wrapper, tasks)

    print_summary(results, args.verbose)


if __name__ == "__main__":
    main()
