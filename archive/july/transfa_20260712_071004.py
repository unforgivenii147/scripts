#!/data/data/com.termux/files/usr/bin/env python

import sys
from pathlib import Path
from multiprocessing import Pool, cpu_count
from deep_translator import GoogleTranslator
from collections import deque


def translate_line(line: str) -> tuple[str, str] | None:
    if not line.strip():
        return None
    text = line.strip()
    try:
        translator = GoogleTranslator(source="fa", target="en")
        time.sleep(0.05)
        result = translator.translate(text)
        return (text, result)
    except Exception:
        return None


def translate_file(fpath: Path) -> None:
    with fpath.open("r", encoding="utf-8") as infile:
        linez = infile.readlines()
    outf = f"{fpath.stem}_eng{fpath.suffix}"
    outpath = fpath.parent / outf
    with Pool(cpu_count()) as pool:
        with outpath.open("w", encoding="utf-8") as f:
            batch = deque(maxlen=100)
            for result in pool.imap_unordered(translate_line, linez, chunksize=10):
                if result:
                    text, translated = result
                    batch.append(f"{text} = {translated}\n")
                    if len(batch) == 100:
                        f.writelines(batch)
                        batch.clear()
            if batch:
                f.writelines(batch)


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else list(Path.cwd().rglob("*"))
    
    for item in paths:
        fpath = Path(item)
        if fpath.is_file():
            translate_file(fpath)
        elif fpath.is_dir():
            for file in fpath.rglob("*"):
                if file.is_file():
                    translate_file(file)


if __name__ == "__main__":
    main()
