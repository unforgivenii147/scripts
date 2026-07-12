#!/data/data/com.termux/files/usr/bin/env python
import sys
import os
import sqlite3
import json
import base64

def serialize_value(v):
    # Convert bytes (BLOB) to base64 string, leave other types as-is
    if isinstance(v, (bytes, bytearray)):
        return {"__blob_base64": base64.b64encode(v).decode("ascii")}
    return v

def row_to_dict(row):
    return {k: serialize_value(row[k]) for k in row.keys()}

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_sqlite_to_json.py <sqlite-file>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not os.path.isfile(db_path):
        print(f"File not found: {db_path}")
        sys.exit(1)

    out_path = db_path + ".json"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get user tables (skip sqlite internal tables)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]

    output = {}
    for table in tables:
        # Use safe quoting for table name
        cur.execute(f'PRAGMA table_info("{table}");')
        cols = [r["name"] for r in cur.fetchall()]  # not strictly needed, but ensures table exists
        cur.execute(f'SELECT * FROM "{table}";')
        rows = [row_to_dict(row) for row in cur.fetchall()]
        output[table] = rows

    conn.close()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(tables)} tables to {out_path}")

if __name__ == "__main__":
    main()
