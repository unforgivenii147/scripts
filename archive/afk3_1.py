#!/data/data/com.termux/files/usr/bin/python
import ast
import argparse


class ImportRemover(ast.NodeTransformer):
    def __init__(self, unused_imports):
        self.unused_imports = unused_imports

    def visit_Import(self, node):
        # Filter names in import statements
        new_names = [n for n in node.names if n.name not in self.unused_imports]
        if not new_names:
            return None  # Remove the entire line if no imports left
        node.names = new_names
        return node

    def visit_ImportFrom(self, node):
        # Filter names in from-import statements
        new_names = [n for n in node.names if n.name not in self.unused_imports]
        if not new_names:
            return None
        node.names = new_names
        return node


def get_unused_imports(file_path):
    with open(file_path, "r") as f:
        tree = ast.parse(f.read())

    imported_names = {}
    used_names = set()

    # Walk the tree to find imports and usages
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names[name] = node

        # Track usages (names being read/called)
        elif isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # This handles cases like 'os.path', we track 'os'
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

    # Determine unused
    unused = {name for name in imported_names if name not in used_names}
    return tree, unused


def clean_file(input_file, output_file):
    tree, unused = get_unused_imports(input_file)

    if not unused:
        print("No unused imports found.")
        return

    print(f"Removing: {', '.join(unused)}")

    # Transform AST
    transformer = ImportRemover(unused)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    # Note: Using ast.unparse (available in Python 3.9+) to regenerate source
    with open(output_file, "w") as f:
        f.write(ast.unparse(new_tree))
    print(f"Cleaned code written to `{output_file}`")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Python file to clean")
    args = parser.parse_args()

    clean_file(args.file, args.file)
