#!/data/data/com.termux/files/usr/bin/python
"""
Translate non-English comments, docstrings, and print() strings
in Python files recursively from the current directory.
"""

import ast
import io
import time
import tokenize
import multiprocessing
from pathlib import Path

from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory
from dh import DOC_TH1, DOC_TH2

DetectorFactory.seed = 0  # Make results deterministic


# ── config ────────────────────────────────────────────────────────────────────
TARGET_LANG = "en"
DELAY_SECONDS = 0.5  # pause between translator calls (per worker)
MAX_WORKERS = 4  # parallel file workers
# ─────────────────────────────────────────────────────────────────────────────
# Add near the top of the file, after imports
SHEBANG_PREFIX = "#!/"
KNOWN_ENGLISH_TOKENS = {
    "TODO",
    "FIXME",
    "HACK",
    "XXX",
    "NOTE",
    "BUG",
    "pylint",
    "noqa",
    "type: ignore",
    "pragma",
    "coding:",
    "encoding:",
    "charset:",
    "DRYRUN",
    "DRY-RUN",
    "RESCURSIVE MODE ENABLED",
    ".gitignore",
}


def should_skip(text: str) -> bool:
    """Return True if text should NOT be checked for translation."""
    clean = text.strip()

    # Skip shebangs
    if clean.startswith(SHEBANG_PREFIX):
        return True

    # Skip if it's purely ASCII (likely English or code)
    if clean.isascii():
        # But check for known non-English ASCII patterns
        # (e.g., romanized Persian like "salam" would be ASCII)
        # For safety, only skip if it looks like English words
        if any(word in clean.upper() for word in KNOWN_ENGLISH_TOKENS):
            return True
        # Skip if it's a single word or very short
        if len(clean.split()) <= 2 and len(clean) < 30:
            return True

    # Skip if it's just punctuation/symbols
    if not any(c.isalpha() for c in clean):
        return True

    return False


def is_non_english(text: str) -> bool:
    clean = text.strip()
    if not clean or len(clean) < 4:
        return False
    if should_skip(clean):  # still use the skip function
        return False
    try:
        return detect(clean) != "en"
    except Exception:
        return False


def translate_text(text: str) -> str:
    """Translate *text* to English; return original on failure."""
    try:
        result = GoogleTranslator(source="auto", target=TARGET_LANG).translate(text)
        time.sleep(DELAY_SECONDS)
        return result if result else text
    except Exception as exc:
        print(f"  [warn] translation failed: {exc}")
        return text


# ── token-level extraction & replacement ─────────────────────────────────────


def find_print_string_tokens(source: str):
    """
    Yield (start_byte_offset, end_byte_offset, string_value) for every
    string literal that is a direct argument of a print() call.
    Works at the AST level so we get exact locations.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    lines = source.splitlines(keepends=True)
    # build cumulative byte-offset table  (line numbers are 1-based in ast)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode()))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                yield arg.value  # just the string content


def process_file(path: Path) -> bool:
    """
    Translate all non-English tokens in *path*.
    Returns True if the file was modified.
    """
    source = path.read_text(encoding="utf-8")
    tokens = []

    try:
        token_gen = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in token_gen:
            tokens.append(tok)
    except tokenize.TokenError as exc:
        print(f"[skip] {path}: tokenize error – {exc}")
        return False

    # We'll rebuild the source via a list of (start, end, new_text) replacements.
    # Offsets are character positions in the original source.
    lines = source.splitlines(keepends=True)

    def line_col_to_offset(lineno, col):
        """Convert 1-based (line, col) to a character offset in *source*."""
        return sum(len(lines[i]) for i in range(lineno - 1)) + col

    replacements = []  # list of (char_start, char_end, new_source_fragment)

    # ── pass 1: comments ─────────────────────────────────────────────────────
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        raw = tok.string  # e.g.  "#Persian text"
        inner = raw.lstrip("#").strip()
        if not is_non_english(inner):
            continue

        translated = translate_text(inner)
        print(f"  [comment]\n    orig : {inner}\n    trans: {translated}")

        new_comment = "# " + translated
        start = line_col_to_offset(tok.start[0], tok.start[1])
        end = line_col_to_offset(tok.end[0], tok.end[1])
        replacements.append((start, end, new_comment))

    # ── pass 2: string tokens (docstrings + print args) ──────────────────────
    # We need to know which STRING tokens are inside print() calls.
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"[skip] {path}: ast.parse failed – {exc}")
        return False

    # Collect (line, col) of print-arg string constants
    print_arg_positions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    print_arg_positions.add((arg.col_offset, arg.lineno))

    # Collect docstring node positions
    docstring_positions = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ds = node.body[0].value
                docstring_positions.add((ds.col_offset, ds.lineno))

    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue

        tok_col_offset = tok.start[1]
        tok_lineno = tok.start[0]

        is_print_arg = (tok_col_offset, tok_lineno) in print_arg_positions
        is_docstring = (tok_col_offset, tok_lineno) in docstring_positions

        if not (is_print_arg or is_docstring):
            continue

        raw = tok.string

        # detect quote style
        if raw.startswith(DOC_TH1) or raw.startswith(DOC_TH2):
            quote = raw[:3]
        elif raw.startswith('"'):
            quote = '"'
        else:
            quote = "'"

        inner = ast.literal_eval(raw)  # actual string value
        if not isinstance(inner, str) or not is_non_english(inner):
            continue

        translated = translate_text(inner)
        label = "docstring" if is_docstring else "print-str"
        print(f"  [{label}]\n    orig : {inner}\n    trans: {translated}")

        # Escape backslashes and the quote character inside the new value
        escaped = translated.replace("\\", "\\\\").replace(quote, "\\" + quote)
        new_tok = quote + escaped + quote

        start = line_col_to_offset(tok.start[0], tok.start[1])
        end = line_col_to_offset(tok.end[0], tok.end[1])
        replacements.append((start, end, new_tok))

    if not replacements:
        return False

    # ── apply replacements (reverse order so offsets stay valid) ─────────────
    replacements.sort(key=lambda r: r[0], reverse=True)
    src_chars = list(source)
    for char_start, char_end, new_frag in replacements:
        src_chars[char_start:char_end] = list(new_frag)

    new_source = "".join(src_chars)

    # ── validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        print(f"[error] {path}: result is not valid Python – {exc}. Skipping write.")
        return False

    path.write_text(new_source, encoding="utf-8")
    return True


def process_file_wrapper(path_str: str):
    path = Path(path_str)
    #    print(f"\n{'=' * 60}\nProcessing: {path}")
    try:
        changed = process_file(path)
        status = "updated" if changed else "no changes"
    #        print(f"  → {status}")
    except Exception as exc:
        print(f"  [error] {path}: {exc}")


def main():
    py_files = [str(p) for p in Path(".").rglob("*.py") if ".git" not in p.parts]

    if not py_files:
        print("No Python files found.")
        return

    print(f"Found {len(py_files)} Python file(s). Starting with {MAX_WORKERS} workers…\n")

    with multiprocessing.Pool(processes=MAX_WORKERS) as pool:
        pool.map(process_file_wrapper, py_files)


#    print("\nDone.")


if __name__ == "__main__":
    main()
