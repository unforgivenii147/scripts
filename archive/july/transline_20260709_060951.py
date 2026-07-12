#!/data/data/com.termux/files/usr/bin/env python

"""
Translate Chinese characters in text files in-place.
Prioritizes avoiding rate limits over speed.
Only translates Chinese segments within lines, preserving non-Chinese text.
"""

from pathlib import Path
from deep_translator import GoogleTranslator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import sys
import time
import json
import signal
import logging
import re
from datetime import datetime
from dh import mpf_async, get_nobinary
# ── config ────────────────────────────────────────────────────────────────────

DELAY_BETWEEN_SEGMENTS = 0.01  # seconds between each translation request
DELAY_BETWEEN_FILES = 1.0  # seconds between files
MAX_RETRIES = 5  # per-segment retry attempts
PROGRESS_SAVE_EVERY = 10

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

# ── graceful interrupt ────────────────────────────────────────────────────────

_interrupted = False


def _sigint_handler(sig, frame):
    global _interrupted
    print("\n⚠️  Ctrl+C caught — will stop after current segment.")
    _interrupted = True


signal.signal(signal.SIGINT, _sigint_handler)

# ── Chinese detection and segmentation ────────────────────────────────────────

_CHINESE_RANGES = (
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # CJK Extension B
    (0x2A700, 0x2B73F),  # CJK Extension C
    (0x2B740, 0x2B81F),  # CJK Extension D
    (0x2B820, 0x2CEAF),  # CJK Extension E
    (0x2CEB0, 0x2EBEF),  # CJK Extension F
)

_CHINESE_PUNCTUATION = set('，。！？；：、""（）【】《》…—～·　　')


def is_chinese_char(ch: str) -> bool:
    """Check if a single character is Chinese (ideograph or punctuation)."""
    if ch in _CHINESE_PUNCTUATION:
        return True
    return any(lo <= ord(ch) <= hi for lo, hi in _CHINESE_RANGES)


def has_chinese(text: str) -> bool:
    """Check if text contains any Chinese characters."""
    return any(is_chinese_char(ch) for ch in text)


def find_chinese_segments(text: str) -> list[tuple[int, int, str]]:
    """
    Find contiguous Chinese segments in text.
    Returns list of (start_pos, end_pos, segment_text) tuples.
    """
    segments = []
    i = 0
    while i < len(text):
        if is_chinese_char(text[i]):
            start = i
            while i < len(text) and is_chinese_char(text[i]):
                i += 1
            segments.append((start, i, text[start:i]))
        else:
            i += 1
    return segments


def reassemble_line(original: str, translations: dict[tuple[int, int], str]) -> str:
    """
    Reassemble the line by replacing Chinese segments with translations.
    translations maps (start, end) -> translated_text
    """
    result = []
    last_end = 0
    # Sort segments by start position
    for (start, end), translated in sorted(translations.items()):
        # Add non-Chinese part before this segment
        result.append(original[last_end:start])
        # Add translated part
        result.append(translated)
        last_end = end
    # Add remaining non-Chinese part
    result.append(original[last_end:])
    return "".join(result)


# ── encoding-resilient reader ─────────────────────────────────────────────────


def read_text(path: Path) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "cp1252"):
        try:
            return path.read_text(encoding=enc, errors="strict"), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_bytes().decode("utf-8", errors="replace"), "utf-8"


# ── translation with tenacity retry ──────────────────────────────────────────


class RateLimitError(Exception):
    pass


class TranslationError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential_jitter(initial=2, max=60, jitter=3),
    retry=retry_if_exception_type((RateLimitError, TranslationError)),
    before_sleep=before_sleep_log(log, logging.DEBUG),
)
def _translate(text: str) -> str:
    try:
        result = GoogleTranslator(source="auto", target="en").translate(text)
        if result is None:
            raise TranslationError("Translator returned None")
        if has_chinese(result):
            raise TranslationError(f"Result still contains Chinese: {result[:40]}")
        return result
    except (RateLimitError, TranslationError):
        raise
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("429", "rate limit", "too many", "quota")):
            print(f"   ⏳ Rate limited — backing off…")
            raise RateLimitError(str(e))
        if any(k in msg for k in ("timeout", "timed out", "connection")):
            raise TranslationError(str(e))
        raise TranslationError(str(e))


def translate_safe(text: str) -> tuple[str, bool]:
    """Returns (translated_text, success). Never raises."""
    try:
        return _translate(text), True
    except Exception as e:
        print(f"   ❌ Gave up translating: {e}")
        return text, False


# ── progress persistence ──────────────────────────────────────────────────────


def _progress_path(file_path: Path) -> Path:
    return file_path.with_suffix(file_path.suffix + ".xlprogress")


def save_progress(file_path: Path, done: dict, total: int) -> None:
    try:
        # Convert tuple keys to strings for JSON serialization
        serializable_done = {}
        for line_num, segments in done.items():
            if isinstance(segments, dict):
                serializable_segments = {}
                for (start, end), trans in segments.items():
                    key = f"{start},{end}"
                    serializable_segments[key] = trans
                serializable_done[str(line_num)] = serializable_segments
            else:
                serializable_done[str(line_num)] = segments

        state = {
            "file": str(file_path),
            "saved_at": datetime.now().isoformat(),
            "total_lines": total,
            "translations": serializable_done,
        }
        _progress_path(file_path).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"   ⚠️  Could not save progress: {e}")


def load_progress(file_path: Path) -> dict:
    p = _progress_path(file_path)
    if not p.exists():
        return {}
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
        if Path(state.get("file", "")) != file_path:
            return {}

        restored = {}
        for line_num_str, segments in state["translations"].items():
            line_num = int(line_num_str)
            if isinstance(segments, dict):
                restored_segments = {}
                for key, trans in segments.items():
                    start, end = map(int, key.split(","))
                    restored_segments[(start, end)] = trans
                restored[line_num] = restored_segments
            else:
                restored[line_num] = segments

        total_segments = sum(len(v) if isinstance(v, dict) else 1 for v in restored.values())
        print(f"   🔄 Resuming: {len(restored)} lines with {total_segments} segments already done")
        return restored
    except Exception:
        return {}


def drop_progress(file_path: Path) -> None:
    p = _progress_path(file_path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


# ── per-file processor ────────────────────────────────────────────────────────


def process_file(path: Path) -> bool:
    """
    Translate Chinese segments in `path` in-place.
    Returns True on success, False on hard error.
    """
    global _interrupted

    print(f"\n📄 {path}")
    try:
        text, enc = read_text(path)
    except Exception as e:
        print(f"   ❌ Cannot read file: {e}")
        return False

    lines = text.splitlines(keepends=True)

    # Find all lines with Chinese and their segments
    line_segments = {}
    for i, ln in enumerate(lines):
        stripped = ln.rstrip("\r\n")
        segments = find_chinese_segments(stripped)
        if segments:
            line_segments[i] = segments

    if not line_segments:
        print(f"   ✅ No Chinese found — skipping")
        drop_progress(path)
        return True

    total_segments = sum(len(segs) for segs in line_segments.values())
    print(f"   🔍 {len(line_segments)} line(s) with {total_segments} Chinese segment(s) to translate")

    # Load any saved progress
    done: dict = load_progress(path)

    # Initialize done for lines not yet processed
    for line_idx in line_segments:
        if line_idx not in done:
            done[line_idx] = {}

    # Count completed segments
    completed_segments = sum(len(v) if isinstance(v, dict) else 1 for v in done.values())
    segment_count = completed_segments

    for line_idx, segments in line_segments.items():
        if _interrupted:
            save_progress(path, done, len(lines))
            print("   💾 Progress saved. Stopping.")
            return False

        stripped = lines[line_idx].rstrip("\r\n")

        for start, end, chinese_text in segments:
            if _interrupted:
                save_progress(path, done, len(lines))
                print("   💾 Progress saved. Stopping.")
                return False

            # Skip if already translated
            if (start, end) in done[line_idx]:
                continue

            # Translate the Chinese segment
            translated, ok = translate_safe(chinese_text)

            if ok:
                done[line_idx][(start, end)] = translated
                status = "✓"
            else:
                done[line_idx][(start, end)] = chinese_text  # Keep original on failure
                status = "✗"

            segment_count += 1

            # Show progress
            print(
                f"   [{segment_count:>4}/{total_segments}] {status} line {line_idx + 1}: "
                f"{chinese_text[:20].strip()!r} → {translated[:20].strip()!r}"
            )

            # Periodic save
            if segment_count % PROGRESS_SAVE_EVERY == 0:
                save_progress(path, done, len(lines))

            # Rate-limit buffer
            time.sleep(DELAY_BETWEEN_SEGMENTS)

    # Build output with reassembled lines
    out_lines = []
    for i, line in enumerate(lines):
        if i in done and done[i]:
            eol = line[len(line.rstrip("\r\n")) :]  # preserve \n or \r\n
            stripped = line.rstrip("\r\n")
            reassembled = reassemble_line(stripped, done[i])
            out_lines.append(reassembled + eol)
        else:
            out_lines.append(line)

    # Atomic write: write to .tmp then rename
    tmp = path.with_suffix(path.suffix + ".xltmp")
    try:
        tmp.write_text("".join(out_lines), encoding=enc, errors="replace")
        tmp.rename(path)
    except Exception as e:
        print(f"   ❌ Failed to write output: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    drop_progress(path)

    # Count failed segments
    failed_segments = 0
    for line_idx, segments in line_segments.items():
        if line_idx in done:
            for (start, end), trans in done[line_idx].items():
                if has_chinese(trans):
                    failed_segments += 1

    success_segments = total_segments - failed_segments
    print(f"   ✅ Done — {success_segments}/{total_segments} segments translated successfully")
    return True


# ── entry point ───────────────────────────────────────────────────────────────


def main():
    args = sys.argv[1:]

    if args:
        files = [Path(p) for p in args if Path(p).is_file()]
    else:
        files = get_nobinary(Path.cwd())

    for i, f in enumerate(files):
        if _interrupted:
            break
        process_file(f)
        if i < len(files) - 1 and not _interrupted:
            time.sleep(DELAY_BETWEEN_FILES)

    if _interrupted:
        print("\n⚠️  Stopped early. Run again to resume from saved progress.")
    else:
        print("\n✅ All done.")


if __name__ == "__main__":
    main()
