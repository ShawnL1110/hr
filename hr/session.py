"""Server-side sessions. Browser cookies contain opaque random handles only."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time


class Sessions:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,kind TEXT,expires INTEGER,payload TEXT)')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            with c:
                yield c
        finally:
            c.close()

    def put(self, kind, payload, ttl):
        handle = secrets.token_urlsafe(32)
        with self.connect() as c:
            c.execute('DELETE FROM sessions WHERE expires <= ?', (int(time.time()),))
            c.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                      (self.hash(handle), kind, int(time.time())+ttl, json.dumps(payload)))
        return handle

    @staticmethod
    def hash(handle):
        return hashlib.sha256(handle.encode()).hexdigest()

    def get(self, handle, kind, consume=False):
        if not handle or len(handle) > 128:
            return None
        with self.connect() as c:
            if consume:
                c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM sessions WHERE hash=? AND kind=? AND expires>?',
                            (self.hash(handle), kind, int(time.time()))).fetchone()
            if consume:
                c.execute('DELETE FROM sessions WHERE hash=? AND kind=?', (self.hash(handle), kind))
        return json.loads(row[0]) if row else None

    def delete(self, handle):
        if handle:
            with self.connect() as c:
                c.execute('DELETE FROM sessions WHERE hash=?', (self.hash(handle),))
