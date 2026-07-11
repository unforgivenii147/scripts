#!/data/data/com.termux/files/usr/bin/env python
"""
Move Python files that have "import os" in their import section to a subdirectory.
Usage: python move_os_imports.py [root_dir] [target_subdir]

Default: root_dir = '.', target_subdir = 'has_os_import'
"""

import os
import sys
import re
import shutil


def extract_import_section(content):
    """
    Extract the import section from a Python file.
    Returns the import section as a string.
    """
    lines = content.split("\n")
    import_lines = []

    for line in lines:
        stripped = line.strip()
        # Stop if we hit a non-import, non-comment, non-blank line
        if stripped and not stripped.startswith("#") and not stripped.startswith('"') and not stripped.startswith("'"):
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(line)
            else:
                # If we've already collected imports, stop at first non-import line
                if import_lines:
                    break
        else:
            # Keep comments and blank lines within import section
            if import_lines or (not stripped):
                import_lines.append(line)

    return "\n".join(import_lines)


def has_os_import(file_path):
    """
    Check if a Python file has 'import os' or 'from os import' in its import section.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract import section
        import_section = extract_import_section(content)

        # Check for 'import os' or 'from os import'
        # Pattern matches: import os, import os as ..., from os import ...
        patterns = [
            r"^import\s+os\b",  # import os
            r"^import\s+os\s+as\s+\w+",  # import os as something
            r"^from\s+os\s+import\s+",  # from os import ...
        ]

        for line in import_section.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                for pattern in patterns:
                    if re.search(pattern, stripped):
                        return True

        # Also check if 'os.' is used in imports (less common but possible)
        if re.search(r"^import\s+.*\bos\b", import_section, re.MULTILINE):
            return True

        return False

    except (UnicodeDecodeError, IOError) as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return False


def get_python_files(root_dir):
    """
    Get all Python files in the directory tree.
    """
    python_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip the target subdirectory if it exists to avoid moving files already moved
        for filename in filenames:
            if filename.endswith(".py"):
                full_path = os.path.join(dirpath, filename)
                python_files.append(full_path)
    return python_files


def move_files(files, target_dir, root_dir):
    """
    Move files to the target directory while preserving relative paths.
    """
    # Create target directory
    os.makedirs(target_dir, exist_ok=True)

    moved_files = []
    errors = []

    for file_path in files:
        # Get relative path from root
        rel_path = os.path.relpath(file_path, root_dir)

        # Create subdirectory structure in target
        target_path = os.path.join(target_dir, rel_path)
        target_subdir = os.path.dirname(target_path)

        try:
            # Create subdirectories if needed
            os.makedirs(target_subdir, exist_ok=True)

            # Move the file
            shutil.move(file_path, target_path)
            moved_files.append(rel_path)
            print(f"Moved: {rel_path} -> {target_path}")

        except Exception as e:
            errors.append((rel_path, str(e)))
            print(f"Error moving {rel_path}: {e}")

    return moved_files, errors


def main():
    # Parse command line arguments
    root_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    target_dir = sys.argv[2] if len(sys.argv) > 2 else "has_os_import"

    # Validate root directory
    if not os.path.isdir(root_dir):
        print(f"Error: '{root_dir}' is not a valid directory.")
        sys.exit(1)

    print(f"Scanning Python files in: {os.path.abspath(root_dir)}")
    print(f"Target subdirectory: {target_dir}")
    print("-" * 50)

    # Get all Python files
    all_files = get_python_files(root_dir)
    print(f"Found {len(all_files)} Python files")

    # Filter files that have 'import os'
    files_to_move = []
    for file_path in all_files:
        if has_os_import(file_path):
            files_to_move.append(file_path)
            print(f"✓ {os.path.relpath(file_path, root_dir)}")

    print("-" * 50)
    print(f"Found {len(files_to_move)} files with 'import os'")

    if not files_to_move:
        print("No files to move.")
        return

    # Ask for confirmation
    response = input(f"Move these {len(files_to_move)} files to '{target_dir}'? (y/n): ")
    if response.lower() != "y":
        print("Operation cancelled.")
        return

    # Move the files
    print("\nMoving files...")
    moved, errors = move_files(files_to_move, target_dir, root_dir)

    print("-" * 50)
    print(f"Successfully moved {len(moved)} files")
    if errors:
        print(f"Errors: {len(errors)}")
        for file_path, error in errors:
            print(f"  {file_path}: {error}")


if __name__ == "__main__":
    main()
