#!/data/data/com.termux/files/usr/bin/env python


import sys
from pathlib import Path
import time
from deep_translator import GoogleTranslator


def translate_file(fname: str) -> str:
    linez = []
    path = Path(fname)
    with Path(path).open("r", encoding="utf-8") as infile:
        linez = infile.readlines()
    outf = str(path.stem) + "_eng" + str(path.suffix)
    outpath = path.parent / outf
    with Path(outpath).open("a", encoding="utf-8") as f:
        for line in linez:
            if line.strip():
                text = line.strip()
                translator = GoogleTranslator(source="fa", target="en")
                result = translator.translate(text)
                f.write(f"\n{text} = {result}\n")
                time.sleep(0.1)
    return result


if __name__ == "__main__":
    translate_file(sys.argv[1])
