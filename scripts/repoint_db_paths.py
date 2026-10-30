"""Repoint absolute paths in the shipped SQLite database at this checkout.

The database bundled in the repository stores file paths from the machine it
was created on. Any column whose name contains "path" and whose value starts
with that old root is rewritten to the current repository root.
"""
import os
import sqlite3

OLD_ROOTS = [
    r"C:\Users\anshu\OneDrive\Documents\HawkEYE",
    "/app",
]
ROOT = os.path.abspath(os.path.dirname(__file__))
DB = os.path.join(ROOT, "data", "smdpis.db")

con = sqlite3.connect(DB)
tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table'"
)]

total = 0
for table in tables:
    cols = [r[1] for r in con.execute(f"pragma table_info('{table}')")]
    for col in [c for c in cols if "path" in c.lower()]:
        for old in OLD_ROOTS:
            sql = (
                f'update "{table}" set "{col}" = replace("{col}", ?, ?) '
                f'where "{col}" like ?'
            )
            cur = con.execute(sql, (old, ROOT, old + "%"))
            if cur.rowcount > 0:
                print(f"{table}.{col}: {cur.rowcount} row(s) repointed from {old}")
                total += cur.rowcount
con.commit()

print(f"\ntotal rows repointed: {total}\n")
for row in con.execute(
    "select id, status, file_path, processed_path from datasets"
):
    ds_id, status, raw, proc = row
    print(
        f"{ds_id}  {status:<12} raw_exists={os.path.exists(raw) if raw else None}"
        f"  processed_exists={os.path.exists(proc) if proc else None}"
    )
con.close()
