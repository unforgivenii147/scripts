# utils.py
import contextlib
import os
import pathlib
import re
import shutil
import subprocess
from collections import defaultdict

BACKUP_SUFFIX = ".bak"


def list_py_files(root: str, recursive: bool = True):
    out = []
    for d, _, files in os.walk(root):
        out.extend(os.path.join(d, f) for f in files if f.endswith(".py") and not f.endswith(BACKUP_SUFFIX + ".py"))
        if not recursive:
            break
    return out


def ensure_backups(paths) -> None:
    for p in paths:
        if pathlib.Path(p).exists():
            shutil.copy2(p, p + BACKUP_SUFFIX)


def restore_backups(paths):
    restored = []
    for p in paths:
        bak = p + BACKUP_SUFFIX
        if pathlib.Path(bak).exists():
            shutil.copy2(bak, p)
            restored.append(p)
    return restored


def overwrite_file(path: str, content: str, dry_run: bool) -> None:
    if dry_run:
        return
    pathlib.Path(pathlib.Path(path).parent or ".").mkdir(exist_ok=True, parents=True)
    pathlib.Path(path).write_text(content, encoding="utf-8")


def try_format(path: str) -> None:
    with contextlib.suppress(Exception):
        subprocess.run(["ruff", "format", path], check=False)




def _parse_name_from_block(block: str) -> str | None:
    block = block.strip()
    if block.startswith("def "):
        return block[4:].split("(")[0].strip()
    if block.startswith("class "):
        name_part = block[6:].split("(")[0].split(":")[0].strip()
        return name_part
    if "=" in block:
        return block.split("=", 1)[0].strip()
    return None

def _get_referenced_names(block: str) -> set[str]:
    return set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', block))

def topological_sort(blocks: list[str], defined_names: set[str]) -> list[str]:
    """Sort blocks so that dependencies come before dependents."""
    name_to_block = {}
    for b in blocks:
        n = _parse_name_from_block(b)
        if n:
            name_to_block[n] = b

    deps = {}
    for name, block in name_to_block.items():
        refs = _get_referenced_names(block) & defined_names - {name}
        deps[name] = refs

    in_degree = {name: 0 for name in name_to_block}
    for name, refs in deps.items():
        for r in refs:
            if r in in_degree:
                in_degree[name] += 1

    adjacency = {name: [] for name in name_to_block}
    for name, refs in deps.items():
        for r in refs:
            if r in adjacency:
                adjacency[r].append(name)

    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_names = []
    while queue:
        name = queue.pop(0)
        sorted_names.append(name)
        for dependent in adjacency[name]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_names) != len(name_to_block):
        return blocks  # fallback to original order
    return [name_to_block[n] for n in sorted_names]
