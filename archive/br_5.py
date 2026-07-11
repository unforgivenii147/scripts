#!/data/data/com.termux/files/usr/bin/python

import argparse
import mmap
import sys
from pathlib import Path
import pdb

from binaryornot import is_binary
from brotlicffi import compress as brotli_compress
from brotlicffi import decompress as brotli_decompress
from dh import cprint, fsz, get_files, gsz, mpf3

CHUNK_SIZE = 1048576  # 512KB chunks for better memory control
N_JOBS = -1


def compress_in_memory(infile, outfile, mode: int) -> bool:
    """Compress small files in memory with immediate cleanup"""
    try:
        data = infile.read_bytes()
        compressed_data = brotli_compress(data, mode=mode, quality=11)
        outfile.write_bytes(compressed_data)
        return True
    except Exception:
        return False
    finally:
        try:
            del data
        except:
            pass
        try:
            del compressed_data
        except:
            pass


def decompress_in_memory(infile, outfile) -> bool:
    """Decompress small files in memory with immediate cleanup"""
    try:
        data = infile.read_bytes()
        decompressed_data = brotli_decompress(data)
        outfile.write_bytes(decompressed_data)
        return True
    except Exception:
        return False
    finally:
        try:
            del data
        except:
            pass
        try:
            del decompressed_data
        except:
            pass


def compress_chunk(data: bytes, mode: int = 0):
    """Compress a single chunk - returns bytes"""
    return brotli_compress(data, mode=mode, quality=11)


def decompress_chunk(data) -> bytes:
    """Decompress a single chunk - returns bytes"""
    return brotli_decompress(data)


def parallel_compress(in_path: Path, out_path: Path) -> bool:
    """
    Memory-efficient compression using streaming and smaller chunks.
    """
    try:
        mode = 0 if is_binary(in_path) else 1

        file_size = in_path.stat().st_size
        if not file_size:
            return False

        if file_size < CHUNK_SIZE:
            return compress_in_memory(in_path, out_path, mode)

        chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        with out_path.open("wb", buffering=1024 * 1024) as fout:
            with in_path.open("rb") as fin:
                with mmap.mmap(fin.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                    for i in range(chunk_count):
                        start = i * CHUNK_SIZE
                        end = min(start + CHUNK_SIZE, file_size)
                        chunk = mm[start:end]
                        block = compress_chunk(chunk, mode)
                        fout.write(len(block).to_bytes(4, "big"))
                        fout.write(block)
                        del chunk, block
        return True

    except OSError:
        return False


def parallel_decompress(in_path: Path, out_path: Path) -> bool:
    """
    Memory-efficient decompression by reading size-prefixed chunks.
    """
    try:
        file_size = in_path.stat().st_size
        if not file_size:
            return False

        # Try to decompress as a single block first (for small files)
        if file_size < CHUNK_SIZE:
            return decompress_in_memory(in_path, out_path)

        # For larger files, process chunked format
        with out_path.open("wb", buffering=1048576) as fout:
            with in_path.open("rb", buffering=1048576) as fin:
                while True:
                    # Read chunk size prefix (4 bytes)
                    size_bytes = fin.read(4)
                    if not size_bytes:
                        break

                    chunk_size = int.from_bytes(size_bytes, "big")

                    # Read the compressed chunk
                    compressed_chunk = fin.read(chunk_size)
                    if not compressed_chunk:
                        break

                    # Decompress and write
                    block = decompress_chunk(compressed_chunk)
                    fout.write(block)

                    del compressed_chunk, block
        return True

    except Exception:
        return False


def process_compress(path) -> None:
    """Compress a single file"""
    path = Path(path)
    if not path.exists() or path.suffix == ".br":
        return

    before = gsz(path)
    if not before:
        return

    outfile = Path(str(path) + ".br")

    try:
        if parallel_compress(path, outfile):
            path.unlink()
        elif outfile.exists():
            outfile.unlink()

        after = gsz(outfile) if outfile.exists() else 0
        dsz = abs(before - after)
        ratio = after / before * 100 if before > 0 else 0
        reduction = dsz / before * 100
        cprint(f"✓ {outfile.name}", "green", end=" | ")
        cprint(f"{fsz(dsz)} saved | {ratio:.1f}% | {reduction:.1f}%", "cyan")

    finally:
        del before, after, dsz, ratio


def process_decompress(path) -> None:
    """Decompress a single file"""
    path = Path(path)
    if not path.exists() or path.suffix != ".br":
        return

    # Remove .br extension
    outfile = path.with_name(path.name.replace(".br", ""))
    before = gsz(path)
    if not before:
        return

    try:
        if parallel_decompress(path, outfile):
            path.unlink()
        elif outfile.exists():
            outfile.unlink()

        after = gsz(outfile) if outfile.exists() else 0
        dsz = abs(after - before)

        cprint(f"✓ {outfile.name}", "green", end=" | ")
        cprint(f"{fsz(dsz)} extracted", "cyan")

    finally:
        del before, after, dsz


def main() -> int:
    parser = argparse.ArgumentParser(description="Brotli compression tool with parallel processing")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--compress", action="store_true", default=True, help="Compress files (default)")
    group.add_argument("-d", "--decompress", action="store_true", help="Decompress .br files")

    parser.add_argument("files", nargs="*", help="Files to process (defaults to all files in current directory)")

    args = parser.parse_args()

    cwd = Path.cwd()
    before = gsz(cwd)
    pdb.set_trace()
    files = [Path(arg) for arg in args.files] if args.files else get_files(cwd)

    if args.decompress:
        # Filter only .br files for decompression
        files = [f for f in files if f.suffix == ".br"]
        if not files:
            cprint("No .br files found to decompress", "yellow")
            return 1
        cprint(f"Decompressing {len(files)} file(s)...", "blue")
        mpf3(process_decompress, files)
    else:
        # Filter out .br files for compression
        files = [f for f in files if f.suffix != ".br"]
        if not files:
            cprint("No files to compress (excluding .br files)", "yellow")
            return 1
        cprint(f"Compressing {len(files)} file(s)...", "blue")
        mpf3(process_compress, files)

    diff_size = before - gsz(cwd)
    if diff_size > 0:
        cprint(f"✓ Space saved: {fsz(diff_size)}", "green")
    elif diff_size < 0:
        cprint(f"Space used: {fsz(abs(diff_size))}", "yellow")

    return 0


if __name__ == "__main__":
    sys.exit(main())
