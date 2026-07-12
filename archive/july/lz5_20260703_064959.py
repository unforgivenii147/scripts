#!/data/data/com.termux/files/usr/bin/env python
"""
Folder compressor/decompressor using LZ4 with multiprocessing
Usage:
    python script.py -c        # Compress all subfolders
    python script.py -d        # Decompress all .tar.lz4 files
"""

import argparse
import shutil
import tarfile
import lz4.frame
from pathlib import Path
from multiprocessing import Pool, cpu_count


def compress_folder(folder_path):
    """Compress a single folder to .tar.lz4"""
    folder = Path(folder_path)
    if not folder.is_dir():
        return f"Skipped {folder}: Not a directory"

    # Skip if already compressed
    tar_lz4_path = folder.with_suffix(".tar.lz4")
    if tar_lz4_path.exists():
        return f"Skipped {folder}: Already compressed"

    try:
        # Create tar in memory and compress with LZ4
        tar_data = tarfile.open(fileobj=tar_lz4_path.with_suffix(".tar"), mode="w")
        tar_data.add(folder, arcname=folder.name)
        tar_data.close()

        # Compress tar with LZ4 (level 3 for speed)
        with open(tar_lz4_path.with_suffix(".tar"), "rb") as f:
            tar_bytes = f.read()

        compressed = lz4.frame.compress(tar_bytes, compression_level=3)

        with open(tar_lz4_path, "wb") as f:
            f.write(compressed)

        # Remove temporary tar and original folder
        tar_lz4_path.with_suffix(".tar").unlink()
        shutil.rmtree(folder)

        return f"Compressed: {folder} -> {tar_lz4_path}"

    except Exception as e:
        return f"Error compressing {folder}: {e}"


def decompress_file(file_path):
    """Decompress a .tar.lz4 file"""
    file = Path(file_path)
    if not file.suffix == ".lz4" or not file.stem.endswith(".tar"):
        return f"Skipped {file}: Not a tar.lz4 file"

    # Extract folder name (remove .tar suffix)
    folder_name = file.stem[:-4]  # Remove '.tar'
    folder_path = file.parent / folder_name

    # Skip if already exists
    if folder_path.exists():
        return f"Skipped {folder}: Already decompressed"

    try:
        # Read and decompress LZ4 data
        with open(file, "rb") as f:
            compressed_data = f.read()

        decompressed = lz4.frame.decompress(compressed_data)

        # Write temporary tar
        temp_tar = file.with_suffix(".tar")
        with open(temp_tar, "wb") as f:
            f.write(decompressed)

        # Extract tar
        with tarfile.open(temp_tar, "r") as tar:
            tar.extractall(path=file.parent)

        # Clean up
        temp_tar.unlink()
        file.unlink()

        return f"Decompressed: {file} -> {folder_path}"

    except Exception as e:
        return f"Error decompressing {file}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Compress/decompress folders with LZ4")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--compress", action="store_true", help="Compress subfolders")
    group.add_argument("-d", "--decompress", action="store_true", help="Decompress .tar.lz4 files")

    args = parser.parse_args()

    current_dir = Path.cwd()

    # Get items to process
    if args.compress:
        items = [d for d in current_dir.iterdir() if d.is_dir()]
        process_func = compress_folder
        action = "Compressing"
    else:  # decompress
        items = [f for f in current_dir.iterdir() if f.is_file() and f.suffix == ".lz4" and f.stem.endswith(".tar")]
        process_func = decompress_file
        action = "Decompressing"

    if not items:
        print(f"No {'folders' if args.compress else '.tar.lz4 files'} found")
        return

    print(f"{action} {len(items)} items using {cpu_count()} processes...")

    # Process with multiprocessing
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(process_func, items)

    # Print results
    for result in results:
        print(result)

    print(f"\n{action} complete!")


if __name__ == "__main__":
    main()
