#!/data/data/com.termux/files/usr/bin/env python
import sys
import sqlite3
import json
import base64
from pathlib import Path
from multiprocessing import Pool, cpu_count
from functools import partial

def serialize_value(v):
    """Convert bytes (BLOB) to base64 string, leave other types as-is"""
    if isinstance(v, (bytes, bytearray)):
        return {"__blob_base64": base64.b64encode(v).decode("ascii")}
    # Handle non-UTF8 strings by attempting to decode with fallback
    if isinstance(v, str):
        try:
            v.encode('utf-8')  # Validate UTF-8 encoding
        except UnicodeEncodeError:
            return {"__invalid_utf8": base64.b64encode(v.encode('utf-8', errors='replace')).decode("ascii")}
    return v

def row_to_dict(row):
    """Convert sqlite3.Row to dict with serialized values"""
    return {k: serialize_value(row[k]) for k in row.keys()}

def fetch_table_data(args):
    """Fetch data from a single table (for parallel processing)"""
    db_path, table_name = args
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Validate table exists
        cur.execute(f'PRAGMA table_info("{table_name}");')
        cols = cur.fetchall()
        if not cols:
            conn.close()
            return table_name, [], f"Table '{table_name}' has no columns"
        
        # Fetch all rows with UTF-8 error handling
        try:
            cur.execute(f'SELECT * FROM "{table_name}";')
            rows = [row_to_dict(row) for row in cur.fetchall()]
            conn.close()
            return table_name, rows, None
        except UnicodeDecodeError as e:
            # Fallback: fetch with UTF-8 error replacement
            conn.close()
            conn = sqlite3.connect(db_path)
            conn.text_factory = lambda x: x.decode('utf-8', errors='replace')
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(f'SELECT * FROM "{table_name}";')
            rows = [row_to_dict(row) for row in cur.fetchall()]
            conn.close()
            return table_name, rows, f"UTF-8 decoding errors replaced in '{table_name}'"
    
    except Exception as e:
        return table_name, [], f"Error processing table '{table_name}': {str(e)}"

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_sqlite_to_json.py <sqlite-file>")
        sys.exit(1)

    db_path = Path(sys.argv[1])
    if not db_path.is_file():
        print(f"File not found: {db_path}")
        sys.exit(1)

    out_path = db_path.with_suffix(db_path.suffix + ".json")

    # Get list of user tables
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}")
        sys.exit(1)

    if not tables:
        print("No tables found in database")
        sys.exit(1)

    # Process tables in parallel
    num_processes = min(cpu_count(), len(tables))
    print(f"Processing {len(tables)} tables using {num_processes} processes...")
    
    with Pool(processes=num_processes) as pool:
        fetch_func = partial(fetch_table_data, db_path=db_path)
        results = pool.map(fetch_table_data, [(db_path, table) for table in tables])

    # Compile output and collect warnings
    output = {}
    warnings = []
    
    for table_name, rows, warning in results:
        output[table_name] = rows
        if warning:
            warnings.append(warning)

    # Write JSON with UTF-8 error handling
    try:
        with open(out_path, "w", encoding="utf-8", errors="replace") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        print(f"✓ Wrote {len(tables)} tables to {out_path}")
    except Exception as e:
        print(f"Error writing JSON: {e}")
        sys.exit(1)

    # Print any warnings
    if warnings:
        print("\n⚠ Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

if __name__ == "__main__":
    main()
