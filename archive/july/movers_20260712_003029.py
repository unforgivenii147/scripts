# movers.py
import ast
import pathlib
from ast import Assign, ClassDef, FunctionDef, Import, ImportFrom
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache


def make_all(names: list[str]) -> str:
    uniq = sorted(set(names))
    items = ",\n    ".join(f'"{n}"' for n in uniq)
    return f"__all__ = [\n    {items}\n]\n"


@lru_cache(maxsize=256)
def _parse_import_line(imp: str) -> list[str]:
    if imp.startswith("import "):
        return [n.strip().split()[0] for n in imp[7:].split(",")]
    if imp.startswith("from "):
        return [imp.split()[1]]
    return []


def _get_block(lines: list[str], node: Assign | ClassDef | FunctionDef | Import | ImportFrom) -> str:
    start = node.lineno - 1
    end = getattr(node, "end_lineno", start + 1)
    return "\n".join(lines[start:end]) + "\n"


def parse_top_level_items(path: str):
    try:
        src = pathlib.Path(path).open(encoding="utf-8").read()
        tree = ast.parse(src)
    except Exception:
        return [], [], [], []
    lines = src.splitlines()
    funcs, consts, classes, imports = (
        [],
        [],
        [],
        [],
    )
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(_get_block(lines, node))
        elif isinstance(node, ast.FunctionDef):
            funcs.append(_get_block(lines, node))
        elif isinstance(node, ast.ClassDef):
            classes.append(_get_block(lines, node))
        elif isinstance(node, ast.Assign) and (
            len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()
        ):
            consts.append(_get_block(lines, node))
    return funcs, consts, classes, imports


def collect_from_files(paths: list[str]):
    with ThreadPoolExecutor() as ex:
        results = list(ex.map(parse_top_level_items, paths))
    file_map = {}
    (
        all_funcs,
        all_consts,
        all_classes,
        all_imports,
    ) = ([], [], [], [])
    for p, (f, c, cl, im) in zip(paths, results, strict=False):
        file_map[p] = {
            "funcs": f,
            "consts": c,
            "classes": cl,
            "imports": im,
        }
        all_funcs += f
        all_consts += c
        all_classes += cl
        all_imports += im
    return (
        all_funcs,
        all_consts,
        all_classes,
        all_imports,
        file_map,
    )





def build_merged_module(file_map: dict) -> str:
    imports = []
    consts, funcs, classes = [], [], []
    const_names, func_names, class_names = [], [], []
    name_sources: dict[str, str] = {}

    for path, b in file_map.items():
        imports.extend(b["imports"])

        for block in b["consts"]:
            name = _parse_name_from_block(block)  # reuse the helper
            if name in name_sources:
                print(f'WARNING: Constant "{name}" defined in both {name_sources[name]} and {path}')
            name_sources[name] = path
            consts.append(block)
            const_names.append(name)

        for block in b["funcs"]:
            name = _parse_name_from_block(block)
            if name in name_sources:
                print(f'WARNING: Function "{name}" defined in both {name_sources[name]} and {path}')
            name_sources[name] = path
            funcs.append(block)
            func_names.append(name)

        for block in b["classes"]:
            name = _parse_name_from_block(block)
            if name in name_sources:
                print(f'WARNING: Class "{name}" defined in both {name_sources[name]} and {path}')
            name_sources[name] = path
            classes.append(block)
            class_names.append(name)

    # Filter out relative imports before optimisation
    filtered_imports = [imp for imp in imports if not imp.strip().startswith("from .")]

    optimized_imports = _optimize_imports(filtered_imports)

    # Sort functions and classes by dependency order
    all_defined_names = set(const_names + func_names + class_names)
    if funcs:
        funcs = _topological_sort(funcs, all_defined_names)
    if classes:
        classes = _topological_sort(classes, all_defined_names)

    # Build body
    body_parts = []
    if consts:
        body_parts.append("\n".join(consts).strip())
    if funcs:
        body_parts.append("\n\n".join(funcs).strip())
    if classes:
        body_parts.append("\n\n".join(classes).strip())

    body = "\n\n\n".join(part for part in body_parts if part)
    all_block = make_all(const_names + func_names + class_names)

    result = []
    if optimized_imports.strip():
        result.append(optimized_imports.strip())
    if body:
        result.append(body)
    result.append(all_block)

    return "\n\n\n".join(result) + "\n"


def _optimize_imports(import_blocks: list) -> str:
    seen = set()
    merged_imports = defaultdict(list)
    std_imports, third_party, local_imports = [], [], []

    for line in import_blocks:
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)

        if line.startswith("from "):
            parts = line.split()
            module = parts[1]
            import_part = line.split("import", 1)[1].strip()
            names = [n.strip() for n in import_part.replace("(", "").replace(")", "").split(",")]
            merged_imports[module].extend(names)
        elif line.startswith("import "):
            modules = [m.strip() for m in line[7:].split(",")]
            for m in modules:
                if m not in merged_imports:
                    merged_imports[m] = []

    for module, names in merged_imports.items():
        if module.startswith("."):
            local_imports.append((module, names))
        elif "." in module:
            third_party.append((module, names))
        else:
            std_imports.append((module, names))

    def fmt(items):
        lines = []
        for module, names in sorted(items):
            unique_names = sorted(set(n for n in names if n))
            if unique_names:
                names_str = ", ".join(unique_names)
                if len(names_str) > 79:
                    lines.append(f"from {module} import (\n    {names_str.replace(', ', ',\n    ')}\n)")
                else:
                    lines.append(f"from {module} import {names_str}")
            else:
                lines.append(f"import {module}")
        return lines

    result = fmt(std_imports) + fmt(third_party) + fmt(local_imports)
    return "\n".join(result) + "\n\n" if result else ""
