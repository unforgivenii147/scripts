#!/data/data/com.termux/files/usr/bin/env python


"""
Fix regex patterns:
  - Add raw string prefix 'r' to the first argument of re.sub / re.search / re.find /
    re.findall / re.match if it is a non-raw string literal.
  - Then replace double backslashes '\\' with single backslashes '' inside that
    string literal.
Processes all .py files recursively from the current working directory.
Creates a .bak backup of each file before modifying it.
"""

import io
import sys
import tokenize
from pathlib import Path
from typing import List

FUNC_NAMES = {"sub", "search", "find", "findall", "match", "finditer", "subn", "split"}
SKIP_TYPES = {
    tokenize.NL,
    tokenize.COMMENT,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.TYPE_COMMENT,
}


def make_raw_and_fix(token_str: str) -> str:
    prefix_end = 0
    for ch in token_str:
        if ch in ('"', "'"):
            break
        prefix_end += 1
    else:
        return token_str
    prefix = token_str[:prefix_end]
    if "r" in prefix.lower():
        return token_str
    quote_char = token_str[prefix_end]
    quote_len = (
        3 if len(token_str) >= prefix_end + 3 and token_str[prefix_end : prefix_end + 3] == quote_char * 3 else 1
    )
    opening = quote_char * quote_len
    content = token_str[prefix_end + quote_len : -quote_len]
    new_content = content.replace("\\\\", "\\")
    return f"r{prefix}{opening}{new_content}{opening}"


def process_file(path: Path) -> bool:
    try:
        code = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)
        return False
    bakpath = path.with_suffix(path.suffix + ".bak")
    try:
        bakpath.write_text(code, encoding="utf-8")
    except OSError as e:
        print(f"Warning: Could not create backup for {path}: {e}", file=sys.stderr)
        return False
    modifications = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        window = []
        for tok in tokens:
            window.append(tok)
            if len(window) > 10:
                window.pop(0)
            if len(window) >= 5:
                if (
                    window[-5].type == tokenize.NAME
                    and window[-5].string == "re"
                    and window[-4].type == tokenize.OP
                    and window[-4].string == "."
                    and window[-3].type == tokenize.NAME
                    and window[-3].string in FUNC_NAMES
                    and window[-2].type == tokenize.OP
                    and window[-2].string == "("
                    and window[-1].type == tokenize.STRING
                ):
                    str_tok = window[-1]
                    new_str = make_raw_and_fix(str_tok.string)
                    if new_str != str_tok.string:
                        modifications.append((str_tok.start, str_tok.end, new_str))
    except tokenize.TokenError as e:
        print(f"Warning: Tokenizing error in {path}: {e}", file=sys.stderr)
        return False
    if not modifications:
        return False
    lines = code.splitlines(keepends=True)
    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))
    new_code_parts = []
    last_pos = 0
    for start, end, new_str in sorted(modifications, key=lambda x: x[0]):
        start_abs = line_offsets[start[0] - 1] + start[1]
        end_abs = line_offsets[end[0] - 1] + end[1]
        new_code_parts.append(code[last_pos:start_abs])
        new_code_parts.append(new_str)
        last_pos = end_abs
    new_code_parts.append(code[last_pos:])
    new_code = "".join(new_code_parts)
    if new_code != code:
        try:
            path.write_text(new_code, encoding="utf-8")
            print(f"Fixed {path}")
            return True
        except OSError as e:
            print(f"Error writing {path}: {e}", file=sys.stderr)
    return False


def get_pyfiles(directory: Path) -> List[Path]:
    return list(directory.rglob("*.py"))


def main() -> None:
    cwd = Path.cwd()
    args = sys.argv[1:]
    files = []
    if args:
        for arg in args:
            p = Path(arg)
            if p.is_file() and p.suffix == ".py":
                files.append(p)
            elif p.is_dir():
                files.extend(get_pyfiles(p))
    else:
        files = get_pyfiles(cwd)
    if not files:
        print("No Python files found.")
        return
    modified_count = 0
    for file_path in files:
        if process_file(file_path):
            modified_count += 1
    print(f"\nDone. Modified {modified_count}/{len(files)} files.")


if __name__ == "__main__":
    main()
