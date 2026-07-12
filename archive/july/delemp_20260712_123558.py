#!/data/data/com.termux/files/usr/bin/env python
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import scandir as os_scandir
from pathlib import Path


def is_binary(path: (Path | str)) -> bool:
    path = Path(path)
    try:
        with path.open("rb") as f:
            chunk = f.read(CHUNK_SIZE)
        if not chunk:
            return False
        if b"\x00" in chunk:
            return True
        text_chars = bytearray(range(32, 127)) + b"\n\r\t\x08"
        nontext = sum(1 for b in chunk if b not in text_chars)
        return nontext / len(chunk) > ZERO_DOT_THREE
    except Exception:
        return True


def get_nobinary(path: (str | Path)) -> list[Path]:
    return [f for f in get_files(path) if not is_binary(f)]


def get_files(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    ext = tuple(ext) if ext else None
    files = []
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIP_DIRS:
                            stack.append(entry)
                    elif entry.is_file(follow_symlinks=False):
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        if ext is None or entry.name.endswith(ext):
                            files.append(Path(entry.path))
        except (PermissionError, OSError):
            continue

    return sorted(files)


# ANSI escape codes for coloring terminal text
CYAN = "\033[36m"
RESET = "\033[0m"


def process_file(path: Path, max_blank_keep: int) -> tuple[Path, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return (path, 0)

    lines = text.splitlines()
    new_lines = []
    blank_run = 0
    removed = 0

    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run <= max_blank_keep:
                new_lines.append("")
            else:
                removed += 1
        else:
            blank_run = 0
            new_lines.append(line)

    if removed > 0:
        output_text = "\n".join(new_lines) + ("\n" if new_lines else "")
        path.write_text(output_text, encoding="utf-8")

    return (path, removed)


def print_result(path: Path, cwd: Path, removed: int):
    # Try to get the path relative to the current directory
    try:
        rel_path = path.relative_to(cwd)
    except ValueError:
        rel_path = path  # Fallback to absolute if it's outside the cwd

    # Format the number in cyan
    print(f"{rel_path}  {CYAN}{removed}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="Remove blank lines from files recursively.")
    parser.add_argument("-n", type=int, default=1, help="Max number of consecutive blank lines to keep (default: 1).")
    parser.add_argument("targets", nargs="*", help="Files or directories to process (defaults to current directory).")
    args = parser.parse_args()

    cwd = Path.cwd()
    files = []
    if args.targets:
        for target in args.targets:
            p = Path(target)
            if p.is_file():
                files.append(p.resolve())  # Use resolve to ensure path math works smoothly
            elif p.is_dir():
                files.extend(f.resolve() for f in get_nobinary(p))
    else:
        files = [f.resolve() for f in get_nobinary(cwd)]

    if not files:
        print("No files found to process.")
        sys.exit(0)

    if len(files) == 1:
        path, removed = process_file(files[0], args.n)
        print_result(path, cwd, removed)
        sys.exit(0)

    total_removed = 0
    with ThreadPoolExecutor() as exe:
        futures = {exe.submit(process_file, f, args.n): f for f in files}
        for fut in as_completed(futures):
            path, removed = fut.result()
            total_removed += removed
            print_result(path, cwd, removed)

    print(f"\nTotal blank lines removed: {CYAN}{total_removed}{RESET}")


if __name__ == "__main__":
    main()
