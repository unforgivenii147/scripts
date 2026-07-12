#!/data/data/com.termux/files/usr/bin/env python
import re
from pathlib import Path

# Chinese character Unicode range
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def has_chinese(text):
    """Check if text contains Chinese characters"""
    return bool(CHINESE_PATTERN.search(text))


def is_text_file(file_path):
    """Check if file is text by extension"""
    text_ext = {
        ".txt",
        ".log",
        ".md",
        ".json",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".py",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".php",
        ".rb",
        ".go",
        ".rs",
        ".sql",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".csv",
    }
    return file_path.suffix.lower() in text_ext


def find_files_with_chinese(directory="."):
    """Find and print files containing Chinese characters"""
    root = Path(directory)

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue

        if not is_text_file(file_path):
            continue

        try:
            # Try different encodings
            for encoding in ["utf-8", "gbk", "gb2312", "big5"]:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        for line in f:
                            if has_chinese(line):
                                print(file_path.name)
                                break
                        else:
                            continue
                        break
                except:
                    continue
        except:
            pass


if __name__ == "__main__":
    # Scan current directory
    find_files_with_chinese()

    # Or scan specific directory:
    # find_files_with_chinese('/path/to/dir')
