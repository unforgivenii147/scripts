#!/data/data/com.termux/files/usr/bin/env python
import sys
import os
import tty
import termios
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

# --- Data Structures & Analyzer ---


@dataclass
class FSItem:
    path: Path
    name: str
    is_dir: bool
    size: int = 0
    children: List["FSItem"] = field(default_factory=list)
    parent: "FSItem" = None
    flag: str = " "  # 'e'=empty, '!'=error, '@'=symlink


class DiskAnalyzer:
    def __init__(self, root_path: Path):
        self.root_path = root_path.resolve()

    def scan(self) -> FSItem:
        root_item = FSItem(path=self.root_path, name=str(self.root_path), is_dir=True)
        try:
            top_level = list(self.root_path.iterdir())
        except Exception:
            root_item.flag = "!"
            return root_item

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(self._scan_recursive, p): p for p in top_level}
            for future in as_completed(futures):
                child = future.result()
                child.parent = root_item
                root_item.children.append(child)
                root_item.size += child.size

        root_item.children.sort(key=lambda x: x.size, reverse=True)
        return root_item

    def _scan_recursive(self, path: Path) -> FSItem:
        if path.is_symlink():
            return FSItem(path=path, name=path.name, is_dir=False, size=0, flag="@")
        if path.is_file():
            try:
                return FSItem(path=path, name=path.name, is_dir=False, size=path.stat().st_size)
            except Exception:
                return FSItem(path=path, name=path.name, is_dir=False, size=0, flag="!")

        dir_item = FSItem(path=path, name=path.name, is_dir=True)
        try:
            for child in path.iterdir():
                child_item = self._scan_recursive(child)
                child_item.parent = dir_item
                dir_item.children.append(child_item)
                dir_item.size += child_item.size
        except Exception:
            dir_item.flag = "!"

        if not dir_item.children and dir_item.flag == " ":
            dir_item.flag = "e"

        dir_item.children.sort(key=lambda x: x.size, reverse=True)
        return dir_item


# --- Formatting Utilities ---


def format_size(num_bytes: int) -> str:
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:5.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:5.1f} PiB"


def get_progress_bar(item_size: int, max_size: int) -> str:
    if max_size == 0:
        return "[          ]"
    ratio = item_size / max_size
    filled = int(ratio * 10)
    return f"[{'#' * filled}{' ' * (10 - filled)}]"


# --- Keyboard Input Engine (Cross-platform safe wrapper for Unix) ---


def get_key() -> str:
    """Reads a single keypress from standard input in raw terminal mode."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":  # Escape sequences (Arrow keys)
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


# --- UI Renderer ---


def render_gdu_table(current_node: FSItem, selected_idx: int) -> Table:
    table = Table(title=f"Directory: {current_node.path}", title_align="left", show_header=False, box=None, expand=True)

    max_size = max([c.size for c in current_node.children], default=1)

    for idx, item in enumerate(current_node.children):
        is_selected = idx == selected_idx

        # Format metrics
        size_str = format_size(item.size)
        bar_str = get_progress_bar(item.size, max_size)
        flag_str = f"[{item.flag}]" if item.flag != " " else "   "
        name_str = f"{item.name}/" if item.is_dir else item.name

        # Styling matching original gdu colors
        size_txt = Text(size_str, style="green")
        bar_txt = Text(bar_str, style="yellow")
        flag_txt = Text(flag_str, style="magenta")
        name_txt = Text(name_str, style="cyan" if item.is_dir else "white")

        if is_selected:
            # Highlight total row if targeted
            row_style = "reverse bold"
            size_txt.style = row_style
            bar_txt.style = row_style
            flag_txt.style = row_style
            name_txt.style = row_style

        table.add_row(size_txt, bar_txt, flag_txt, name_txt)

    return table


# --- Main Runtime Loop ---


def main():
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    if not target_dir.is_dir():
        print(f"Error: {target_dir} is not a valid directory.")
        sys.exit(1)

    console = Console()
    console.print(f"[bold yellow]Scanning {target_dir.resolve()}...[/bold yellow]")

    analyzer = DiskAnalyzer(target_dir)
    current_node = analyzer.scan()
    selected_idx = 0

    with Live(render_gdu_table(current_node, selected_idx), console=console, screen=True, auto_refresh=False) as live:
        while True:
            live.update(render_gdu_table(current_node, selected_idx), refresh=True)

            key = get_key()

            # Navigation Controls (Vim bindings + standard arrow inputs)
            if key in ("q", "\x03"):  # q or Ctrl+C
                break
            elif key in ("\x1b[A", "k"):  # Up Arrow / k
                if selected_idx > 0:
                    selected_idx -= 1
            elif key in ("\x1b[B", "j"):  # Down Arrow / j
                if selected_idx < len(current_node.children) - 1:
                    selected_idx += 1
            elif key in ("\x1b[C", "l", "\r"):  # Right Arrow / l / Enter
                if current_node.children:
                    target = current_node.children[selected_idx]
                    if target.is_dir and target.children:
                        current_node = target
                        selected_idx = 0
            elif key in ("\x1b[D", "h", "\x1b"):  # Left Arrow / h / Escape
                if current_node.parent:
                    # Find old index in parent array to prevent cursor jump loss
                    old_node = current_node
                    current_node = current_node.parent
                    try:
                        selected_idx = current_node.children.index(old_node)
                    except ValueError:
                        selected_idx = 0


if __name__ == "__main__":
    main()
