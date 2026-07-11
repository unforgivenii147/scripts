#!/data/data/com.termux/files/usr/bin/env python
"""
Change Python shebang in all Python files to Termux path.
Usage: python change_shebang.py
"""

import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
from typing import Optional

# The new shebang to use
NEW_SHEBANG = "#!/data/data/com.termux/files/usr/bin/env python"

# Pattern to match shebang lines
SHEBANG_PATTERN = re.compile(r"^#!.*python[23]?(?:\.\d+)?(?:[ \t]+.*)?$", re.MULTILINE)


def process_file(file_path: Path) -> tuple[Path, bool, Optional[str]]:
    """
    Process a single file: read, update shebang, write back if changed.

    Returns:
        tuple: (file_path, was_changed, error_message)
    """
    try:
        # Read the file content
        content = file_path.read_text(encoding="utf-8")

        # Check if file has a shebang
        if not content.startswith("#!"):
            return file_path, False, None

        # Check if shebang contains 'python'
        first_line = content.split("\n")[0] if "\n" in content else content
        if "python" not in first_line.lower():
            return file_path, False, None

        # Check if already has the new shebang
        if first_line.strip() == NEW_SHEBANG:
            return file_path, False, None

        # Replace the first line with new shebang
        lines = content.split("\n")
        lines[0] = NEW_SHEBANG
        new_content = "\n".join(lines)

        # Write back to file
        file_path.write_text(new_content, encoding="utf-8")
        return file_path, True, None

    except Exception as e:
        return file_path, False, str(e)


def find_python_files(directory: Path) -> list[Path]:
    """
    Find all Python files in the directory and subdirectories.
    """
    python_files = []

    # Common Python file extensions
    extensions = {".py", ".pyw", ".pyx", ".pxd", ".pyi"}

    for file_path in directory.rglob("*"):
        if file_path.is_file() and file_path.suffix in extensions:
            python_files.append(file_path)
        # Also check files without extension that might be Python scripts
        elif file_path.is_file() and file_path.stem and "." not in file_path.name:
            # Check if it has a shebang with python
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_line = f.readline()
                    if first_line.startswith("#!") and "python" in first_line.lower():
                        python_files.append(file_path)
            except (UnicodeDecodeError, IOError):
                # Skip binary files or files we can't read
                pass

    return python_files


def main():
    """Main function to process all Python files in the current directory."""
    current_dir = Path.cwd()

    print(f"Searching for Python files in: {current_dir}")

    # Find all Python files
    python_files = find_python_files(current_dir)

    if not python_files:
        print("No Python files found.")
        return

    print(f"Found {len(python_files)} Python files.")

    # Process files in parallel
    changed_files = []
    errors = []
    skipped_files = []

    # Use ProcessPoolExecutor for parallel processing
    with ProcessPoolExecutor() as executor:
        # Submit all tasks
        future_to_file = {executor.submit(process_file, file_path): file_path for file_path in python_files}

        # Process completed tasks
        for future in as_completed(future_to_file):
            file_path, was_changed, error = future.result()

            if error:
                errors.append((file_path, error))
            elif was_changed:
                changed_files.append(file_path)
            else:
                skipped_files.append(file_path)

    # Print summary
    print("\n" + "=" * 50)
    print(f"✅ Changed: {len(changed_files)} files")
    print(f"⏭️  Skipped: {len(skipped_files)} files (no change needed)")
    print(f"❌ Errors: {len(errors)} files")

    if changed_files:
        print("\nChanged files:")
        for file_path in changed_files[:10]:  # Show first 10
            print(f"  - {file_path}")
        if len(changed_files) > 10:
            print(f"  ... and {len(changed_files) - 10} more")

    if errors:
        print("\nErrors:")
        for file_path, error in errors[:5]:  # Show first 5
            print(f"  - {file_path}: {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")

    # Exit with error code if there were errors
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
