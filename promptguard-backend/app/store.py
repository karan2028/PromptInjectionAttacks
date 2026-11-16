"""SQLite summaries only: no task/source text or raw model responses are persisted."""
import json
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        self.path = path
        if path == ":memory:":
            raise ValueError("Use a file path: the store opens one connection per operation")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, summary TEXT NOT NULL
            )""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def add(self, record):
        with self.connect() as con:
            con.execute("INSERT INTO simulations(id,created_at,summary) VALUES(?,?,?)",
                        (record["id"], record["created_at"], json.dumps(record)))

    def list(self, limit=50, offset=0):
        with self.connect() as con:
            total = con.execute("SELECT count(*) FROM simulations").fetchone()[0]
            records = con.execute("SELECT summary FROM simulations ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "records": [json.loads(r[0]) for r in records]}

    def get(self, record_id):
        with self.connect() as con:
            row = con.execute("SELECT summary FROM simulations WHERE id=?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else None
