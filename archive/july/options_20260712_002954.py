# options.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Options:
    mode: str
    root: str = "."
    backup: bool = True
    format: bool = False
    verbose: bool = True
    undo: bool = False
    single: bool = True
