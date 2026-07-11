#!/data/data/com.termux/files/usr/bin/env python
"""
Strip comments and docstrings from Python files recursively (in-place).

This version:
- Preserves module-level docstring.
- Removes function/class docstrings. If a function/class body becomes empty after
  removing the docstring, inserts `pass` to keep syntax valid.
- Removes comments except it preserves:
    - Shebang (#!) on first line.
    - Top-of-file encoding/coding declarations and top-of-file "# type" / "# fmt" comments.
    - Any inline comment anywhere in the file that contains "type:" or "fmt:" (case-insensitive),
      e.g. "# type: ignore" or "# fmt: off".
- Uses pathlib and parallel processing (ProcessPoolExecutor).
- Validates transformed source with ast.parse before writing.
- Updates files in-place and only reports files that changed.
- Uses astor.to_source so it works on Python versions < 3.9.
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import tokenize
import concurrent.futures
import multiprocessing

try:
    import astor
except Exception:
    print("This script requires the 'astor' package. Install with: pip install astor", file=sys.stderr)
    sys.exit(2)


class DocstringStripper(ast.NodeTransformer):
    """
    Remove docstrings from FunctionDef, AsyncFunctionDef, ClassDef.
    Do NOT remove module docstring here (we preserve it).
    If a function/class body becomes empty after removing docstring, insert ast.Pass().
    """

    def _maybe_strip_first_docstring(self, node: ast.AST) -> ast.AST:
        body = getattr(node, "body", None)
        if not body:
            return node
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(getattr(first, "value", None), ast.Constant)
            and isinstance(first.value.value, str)
        ):
            # remove the docstring expr
            body.pop(0)
            if not body:
                body.append(ast.Pass())
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._maybe_strip_first_docstring(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._maybe_strip_first_docstring(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        return self._maybe_strip_first_docstring(node)


def extract_prefix_comments_and_shebang(source: str) -> Tuple[str, str]:
    """
    Return (prefix, remainder) where prefix contains:
      - shebang if present on first line,
      - contiguous top-of-file comment lines that include encoding/coding/type/fmt,
      - and blank lines that appear between them and the first non-comment code.
    Other leading comments are dropped (we strip comments generally).
    """
    lines = source.splitlines(keepends=True)
    prefix_lines: List[str] = []
    i = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Shebang only valid at first line
        if i == 0 and line.startswith("#!"):
            prefix_lines.append(line)
            continue

        # Blank lines: if we've started collecting prefix lines, keep them; otherwise skip
        if stripped == "":
            if prefix_lines:
                prefix_lines.append(line)
            else:
                # skip leading blanks until we hit something relevant
                continue
            continue

        if stripped.startswith("#"):
            low = stripped.lower()
            if (
                "coding" in low
                or "encoding" in low
                or "type:" in low
                or low.startswith("# type")
                or "fmt:" in low
                or low.startswith("# fmt")
            ):
                prefix_lines.append(line)
                continue
            # Other top-of-file comments are dropped
            continue

        # Stop at first non-comment non-blank line
        break

    prefix = "".join(prefix_lines)
    remainder = "".join(lines[i:]) if i < len(lines) else ""
    return prefix, remainder


def collect_preserved_inline_comments(source: str) -> Dict[int, List[str]]:
    """
    Scan source with tokenize and collect comments that contain "type:" or "fmt:" (case-insensitive).
    Return a map: line_number -> list of comment strings (including leading '#').
    """
    comments_by_line: Dict[int, List[str]] = {}
    sio = io.StringIO(source)
    try:
        for tok in tokenize.generate_tokens(sio.readline):
            tok_type = tok.type
            tok_string = tok.string
            start_row, _ = tok.start
            if tok_type == tokenize.COMMENT:
                low = tok_string.lower()
                if (
                    "type:" in low
                    or low.strip().lower().startswith("# type")
                    or "fmt:" in low
                    or low.strip().lower().startswith("# fmt")
                ):
                    comments_by_line.setdefault(start_row, []).append(tok_string)
    except tokenize.TokenError:
        # If tokenization fails, return empty; we'll still rely on AST transform.
        return {}
    return comments_by_line


def reattach_inline_comments(new_source: str, preserved_comments: Dict[int, List[str]]) -> str:
    """
    Try to reattach preserved inline comments to the corresponding line numbers in new_source.
    If the corresponding line doesn't exist, append the comment on a new line at the end.
    Avoid duplicating a comment if it already appears on the target line.
    """
    if not preserved_comments:
        return new_source

    new_lines = new_source.splitlines()
    # new_lines is list without trailing newlines
    # We'll operate with 1-based line numbers for mapping
    max_line = len(new_lines)
    used_comments = set()

    for orig_line_no in sorted(preserved_comments):
        for comment in preserved_comments[orig_line_no]:
            target_line_idx = orig_line_no - 1  # 0-based
            if 0 <= target_line_idx < max_line:
                line = new_lines[target_line_idx]
                if comment in line:
                    used_comments.add((orig_line_no, comment))
                    continue
                # Append comment to the line separated by two spaces if non-empty, else place comment as-is
                if line.rstrip() == "":
                    new_lines[target_line_idx] = comment
                else:
                    new_lines[target_line_idx] = line + "  " + comment
                used_comments.add((orig_line_no, comment))
            else:
                # If target line doesn't exist, append at end later
                continue

    # Append any comments that weren't attached because their original line is beyond new_source length
    for orig_line_no in sorted(preserved_comments):
        for comment in preserved_comments[orig_line_no]:
            if (orig_line_no, comment) in used_comments:
                continue
            # append as its own line
            new_lines.append(comment)
            used_comments.add((orig_line_no, comment))

    return "\n".join(new_lines) + ("\n" if not new_source.endswith("\n") else "")


def process_file(path: Path) -> Tuple[str, bool, Optional[str]]:
    """
    Process a single file.
    Returns (str(path), changed_bool, error_message_or_None).
    """
    try:
        with tokenize.open(path) as f:
            original = f.read()
            encoding = f.encoding
    except Exception as exc:
        return str(path), False, f"read-error: {exc}"

    if not original.strip():
        return str(path), False, None

    # Collect inline comments to preserve (type/fmt)
    preserved_inline_comments = collect_preserved_inline_comments(original)

    # Extract prefix (shebang, top-of-file coding/type/fmt lines)
    prefix, _ = extract_prefix_comments_and_shebang(original)

    # Parse AST and preserve module docstring by not removing Module docstring
    try:
        tree = ast.parse(original)
    except SyntaxError as exc:
        return str(path), False, f"syntax-error-original: {exc}"

    # Transform AST to remove function/class docstrings and add pass as needed
    stripper = DocstringStripper()
    new_tree = stripper.visit(tree)
    ast.fix_missing_locations(new_tree)

    try:
        # Use astor to convert AST back to source (works on older Python versions)
        new_source_body = astor.to_source(new_tree)
    except Exception as exc:
        return str(path), False, f"unparse-failed: {exc}"

    # astor.to_source may not end with newline
    if not new_source_body.endswith("\n"):
        new_source_body = new_source_body + "\n"

    # Reattach prefix if present
    if prefix:
        if not prefix.endswith("\n"):
            prefix = prefix + "\n"
        new_source = prefix + new_source_body
    else:
        new_source = new_source_body

    # Reattach preserved inline comments onto new_source
    new_source = reattach_inline_comments(new_source, preserved_inline_comments)

    # Ensure final trailing newline
    if not new_source.endswith("\n"):
        new_source = new_source + "\n"

    # Validate new source parses
    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        return str(path), False, f"syntax-error-transformed: {exc}"

    # If no change, do nothing
    if new_source == original:
        return str(path), False, None

    # Write back
    try:
        with open(path, "w", encoding=encoding, newline="\n") as f:
            f.write(new_source)
    except Exception as exc:
        return str(path), False, f"write-error: {exc}"

    return str(path), True, None


def should_skip_path(p: Path) -> bool:
    parts = {part.lower() for part in p.parts}
    skip_indicators = {".git", "__pycache__", "venv", ".venv", "env", ".env", "node_modules"}
    if parts & skip_indicators:
        return True
    return False


def collect_py_files(cwd: Path) -> List[Path]:
    files: List[Path] = []
    for p in cwd.rglob("*.py"):
        if should_skip_path(p):
            continue
        if p.is_symlink():
            continue
        files.append(p)
    return files


def main() -> int:
    cwd = Path.cwd()
    files = collect_py_files(cwd)
    if not files:
        print("No .py files found.")
        return 0

    changed: List[str] = []
    errors: List[Tuple[str, str]] = []

    workers = max(1, min(32, multiprocessing.cpu_count()))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, p): p for p in files}
        for fut in concurrent.futures.as_completed(futures):
            try:
                path_str, did_change, err = fut.result()
            except Exception as exc:
                p = futures[fut]
                errors.append((str(p), f"worker-exception: {exc}"))
            else:
                if err:
                    errors.append((path_str, err))
                elif did_change:
                    changed.append(path_str)

    if changed:
        print("Files changed:")
        for p in sorted(changed):
            print(f"  {p}")
    else:
        print("No files were changed.")

    if errors:
        print("\nFiles with errors (left unchanged):")
        for p, e in errors:
            print(f"  {p}: {e}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
