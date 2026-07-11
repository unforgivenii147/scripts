#!/usr/bin/env python3
"""
Remove unused imports from Python files using AST analysis.
Processes single file or directory recursively with multiprocessing.
"""

import sys
import ast
from pathlib import Path
from multiprocessing import Pool, cpu_count
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor


@dataclass
class ImportInfo:
    """Information about an import statement."""

    name: str
    alias: Optional[str]
    line: int
    col: int
    end_line: int
    is_from_import: bool
    module: Optional[str] = None
    names: List[str] = None


class ImportAnalyzer(ast.NodeVisitor):
    """Analyzes Python file to find imports and used names."""

    def __init__(self) -> None:
        self.imports = []  # List of ImportInfo objects
        self.used_names = set()  # Names that are used in the code
        self.defined_names = set()  # Names defined in the current scope
        self.current_scope = []  # Stack of scopes

    def visit_Import(self, node) -> None:
        """Handle 'import module' statements."""
        for alias in node.names:
            # Extract the base name (before .)
            base_name = alias.name.split(".")[0]
            self.imports.append(
                ImportInfo(
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                    col=node.col_offset,
                    end_line=node.end_lineno or node.lineno,
                    is_from_import=False,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node) -> None:
        """Handle 'from module import name' statements."""
        if node.module is None:  # Skip relative imports without module
            self.generic_visit(node)
            return

        for alias in node.names:
            if alias.name == "*":  # Skip star imports (can't safely remove)
                continue

            self.imports.append(
                ImportInfo(
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                    col=node.col_offset,
                    end_line=node.end_lineno or node.lineno,
                    is_from_import=True,
                    module=node.module,
                    names=[alias.name],
                )
            )
        self.generic_visit(node)

    def visit_Name(self, node) -> None:
        """Track name usage."""
        if isinstance(node.ctx, (ast.Load, ast.AugLoad)):
            self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node) -> None:
        """Track function definitions and their arguments."""
        self.defined_names.add(node.name)
        # Add function arguments to defined names
        for arg in node.args.args:
            self.defined_names.add(arg.arg)
        if node.args.vararg:
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defined_names.add(node.args.kwarg.arg)
        self.generic_visit(node)

    def visit_ClassDef(self, node) -> None:
        """Track class definitions."""
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node) -> None:
        """Track variable assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_names.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        self.defined_names.add(elt.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        """Track annotated assignments (Python 3.6+)."""
        if isinstance(node.target, ast.Name):
            self.defined_names.add(node.target.id)
        self.generic_visit(node)

    def visit_alias(self, node) -> None:
        """Track aliased imports usage."""
        # If alias is used, mark the original name as used
        if node.asname:
            if node.asname in self.used_names:
                self.used_names.add(node.name.split(".")[0])
        self.generic_visit(node)


class ImportRemover:
    """Removes unused imports from Python files using AST analysis."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.removed_imports = []

    def analyze(self) -> List[ImportInfo]:
        """Analyze file to find unused imports."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the AST
            tree = ast.parse(content, filename=str(self.file_path))

            # Analyze usage
            analyzer = ImportAnalyzer()
            analyzer.visit(tree)

            # Find unused imports
            unused_imports = []
            for imp in analyzer.imports:
                # Determine the actual name to check
                name_to_check = imp.alias if imp.alias else imp.name

                # Handle from-import with multiple names
                if imp.is_from_import and imp.names:
                    # This is simplified; for complex from-imports we need to parse differently
                    pass

                # Check if name is used and not defined elsewhere
                if name_to_check not in analyzer.used_names and name_to_check not in analyzer.defined_names:
                    unused_imports.append(imp)

            return unused_imports

        except SyntaxError as e:
            print(f"Syntax error in {self.file_path}: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Error analyzing {self.file_path}: {e}", file=sys.stderr)
            return []

    def remove_unused_imports(self, unused_imports: List[ImportInfo]) -> List[str]:
        """Remove unused imports from the file."""
        if not unused_imports:
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Group imports by line to remove entire lines
            lines_to_remove = sorted(set([imp.line for imp in unused_imports]), reverse=True)

            removed_imports = []
            for line_num in lines_to_remove:
                if 1 <= line_num <= len(lines):
                    # Get the line content and strip it
                    line_content = lines[line_num - 1].rstrip()

                    # Check if this line has other imports not being removed
                    # For simplicity, we'll remove the whole line
                    # In a more sophisticated version, you'd parse multi-import lines

                    # Remove the line
                    lines.pop(line_num - 1)

                    # Find which imports were on this line
                    for imp in unused_imports:
                        if imp.line == line_num:
                            import_name = imp.alias if imp.alias else imp.name
                            removed_imports.append(f"{import_name} (line {line_num})")

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
        unused_imports = self.analyze()
        if unused_imports:
            removed = self.remove_unused_imports(unused_imports)
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
            if any(
                part.startswith(".") or part in ["__pycache__", "venv", "env", ".venv", "node_modules"]
                for part in file_path.parts
            ):
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
    main()
