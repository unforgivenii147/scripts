#!/data/data/com.termux/files/usr/bin/python

"""
Termux script creator utility.

Creates executable scripts from clipboard content with automatic
shebang detection and environment-specific optimizations.
"""

import ast
import subprocess
import sys
from pathlib import Path
from typing import Final

TERMUX_PYTHON: Final[str] = "#!/data/data/com.termux/files/usr/bin/python\n"
TERMUX_BASH: Final[str] = "#!/data/data/com.termux/files/usr/bin/bash\n"
EXECUTABLE_PERMISSIONS: Final[int] = 0o755


PYTHON_INDICATORS: Final[tuple[str, ...]] = (
    "import ",
    "from ",
    "def ",
    "class ",
    "async def ",
    "async ",
    "@",
    "with ",
    "try:",
    "if __name__",
)


BASH_INDICATORS: Final[tuple[str, ...]] = (
    "echo ",
    "cd ",
    "export ",
    "set ",
    "if [",
    "if [[",
    "for ",
    "while ",
    "case ",
    "source ",
    "#!/bin/sh",
    "#!/bin/bash",
    "$(",
    "${",
    "`",
)


SCRIPT_DIRS: Final[set[Path]] = {
    Path.home() / "bin",
    Path.home() / "bashbin",
}


def get_clipboard() -> str:
    """Get clipboard content using termux-clipboard-get.

    Returns:
        Clipboard content as string.

    Raises:
        SystemExit: If clipboard retrieval fails.
    """
    try:
        content = subprocess.check_output(
            ["termux-clipboard-get"],
            text=True,
            stderr=subprocess.PIPE,
        )
        return content
    except subprocess.CalledProcessError as e:
        print(f"Error getting clipboard: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: termux-clipboard-get not found", file=sys.stderr)
        sys.exit(1)


def strip_python_strings_and_comments(code: str) -> str:
    """Remove strings and comments from Python code for analysis.

    This helps identify Python code even when it starts with
    docstrings or contains strings that might confuse detection.

    Args:
        code: Python source code.

    Returns:
        Code with strings and comments removed.
    """
    try:
        tree = ast.parse(code)

        class StringCommentStripper(ast.NodeTransformer):
            """Remove string expressions and comments from AST."""

            def visit_Expr(self, node):
                """Remove string expressions (docstrings)."""
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return None
                return node

            def visit_Constant(self, node):
                """Replace string constants with empty string."""
                if isinstance(node.value, str):
                    return ast.Constant(value="")
                return node

        stripper = StringCommentStripper()
        stripped_tree = stripper.visit(tree)
        ast.fix_missing_locations(stripped_tree)

        if hasattr(ast, "unparse"):
            return ast.unparse(stripped_tree)

        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            tree.body = tree.body[1:]

        return ast.unparse(tree) if hasattr(ast, "unparse") else code

    except SyntaxError:
        return code
    except Exception:
        return code


def detect_shebang(content: str) -> str | None:
    """Detect the appropriate shebang for the given content.

    Uses multiple strategies to identify Python code:
    1. Check for explicit shebang
    2. Validate as Python AST
    3. Check for Python indicators after stripping strings/comments
    4. Check for shell indicators

    Args:
        content: Script content to analyze.

    Returns:
        Appropriate shebang string or None if undetermined.
    """
    stripped = content.lstrip()

    if stripped.startswith("#!"):
        shebang_line = stripped.split("\n", 1)[0].lower()
        if "python" in shebang_line:
            return TERMUX_PYTHON
        if "bash" in shebang_line or "sh" in shebang_line:
            return TERMUX_BASH

    try:
        ast.parse(content)
        return TERMUX_PYTHON
    except SyntaxError:
        pass

    stripped_code = strip_python_strings_and_comments(content)
    stripped_lines = stripped_code.lstrip()

    for indicator in PYTHON_INDICATORS:
        if stripped_lines.startswith(indicator):
            return TERMUX_PYTHON

    if any(line.lstrip().startswith("@") for line in stripped_code.splitlines()[:5]):
        return TERMUX_PYTHON

    for indicator in BASH_INDICATORS:
        if indicator in stripped[:200]:
            return TERMUX_BASH

    python_score = 0
    bash_score = 0

    for line in stripped_code.splitlines()[:10]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if any(line.startswith(ind) for ind in PYTHON_INDICATORS):
            python_score += 1
        elif any(ind in line for ind in BASH_INDICATORS):
            bash_score += 1

    if python_score > bash_score:
        return TERMUX_PYTHON
    elif bash_score > python_score:
        return TERMUX_BASH

    return None


def create_symlink(target: Path) -> None:
    """Create a symlink without file extension in the same directory.

    Args:
        target: Target file to create symlink for.
    """
    if target.suffix:
        symlink_path = target.parent / target.stem

        if symlink_path.exists():
            if symlink_path.is_symlink():
                print(f"Symlink already exists.")
            else:
                print(f"Warning: {symlink_path} exists but is not a symlink")
            return

        try:
            symlink_path.symlink_to(target)
            print(f"Created symlink: {symlink_path} -> {target}")
        except OSError as e:
            print(f"Error creating symlink: {e}", file=sys.stderr)


def main() -> None:
    """Main entry point for the script creator."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <output_filename>", file=sys.stderr)
        sys.exit(1)

    out_file = Path(sys.argv[1])
    cwd = Path.cwd()
    is_script_dir = cwd in SCRIPT_DIRS

    content = get_clipboard()

    if not content.strip():
        print("Warning: Clipboard is empty, creating empty file")
        content = "\n"

    if is_script_dir and not content.lstrip().startswith("#!"):
        shebang = detect_shebang(content)
        if shebang:
            content = shebang + content
    #            print(f"Added shebang: {shebang.strip()}")

    lines = content.splitlines()
    if len(lines) > 1 and lines[0].startswith("#!") and lines[1].startswith("#!"):
        lines.pop(0)
        content = "\n".join(lines) + "\n"
        print("Fixed double shebang")

    if not content.endswith("\n"):
        content += "\n"

    try:
        out_file.write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"Error writing file: {e}", file=sys.stderr)
        sys.exit(1)

    if is_script_dir:
        try:
            out_file.chmod(EXECUTABLE_PERMISSIONS)
        except OSError as e:
            print(f"Error setting permissions: {e}", file=sys.stderr)

        create_symlink(out_file)


if __name__ == "__main__":
    main()
