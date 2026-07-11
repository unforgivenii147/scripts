#!/data/data/com.termux/files/usr/bin/python
import ast
import sys
from pathlib import Path

from dh import cprint, fsz, get_pyfiles, gsz, have_doc, mpf3

cwd = Path.cwd()


class DocstringRemover(ast.NodeTransformer):
    def _remove_docstring(self, node):
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            # Remove the docstring (first statement is a string expression)
            if len(node.body) == 1:
                # Avoid empty body: replace with `pass`
                node.body = [ast.Pass()]
            else:
                node.body = node.body[1:]
        return node

    def visit_Module(self, node):
        # Only visit children – do NOT remove the module docstring.
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        return self._remove_docstring(node)


def process_file(path: Path) -> None:
    before = gsz(path)
    try:
        code = path.read_text(encoding="utf-8")
        if not have_doc(code):
            return

        # Preserve shebang line if present
        first_line = ""
        if code.startswith("#!"):
            lines = code.splitlines(keepends=True)
            first_line = lines[0]
            code = "".join(lines[1:])

        # Parse, transform, and unparse in one go
        tree = ast.parse(code)
        transformer = DocstringRemover()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        newcode = ast.unparse(new_tree)

        if first_line:
            newcode = first_line + newcode

        # Safety check: ensure the result is valid Python
        try:
            ast.parse(newcode)
        except SyntaxError:
            cprint(f"❌ Syntax error after transformation: {path.name}", "red")
            del tree, new_tree, code, newcode, transformer, before, first_line
            return

        # Skip writing if nothing changed (avoid unnecessary I/O)
        if len(newcode.strip()) == len(code.strip()):
            cprint(f"{path.name} (no change)", "grey")
            del tree, new_tree, code, newcode, transformer, before, first_line
            return

        path.write_text(newcode, encoding="utf-8")
        after = gsz(path)
        dsz = before - after
        if dsz:
            ratio = dsz / before * 100 if before else 0
            print(f"✅ {path.name}", end=" | ")
            cprint(f"{fsz(dsz)} | {ratio:.1f}%", "cyan")
        else:
            cprint(f"{path.name} (no change)", "grey")

    except Exception as e:
        cprint(f"❌ {path.name}: {e}", "yellow")
    finally:
        # Clean up large objects (optional, helps with memory pressure)
        del before


def main() -> None:
    args = sys.argv[1:]
    files = [Path(p) for p in args] if args else get_pyfiles(cwd)
    if not files:
        print("No Python files found.")
        return
    if len(files) == 1:
        process_file(files[0])
        sys.exit(0)
    mpf3(process_file, files)


if __name__ == "__main__":
    main()
