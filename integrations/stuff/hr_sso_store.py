"""Private HR authorization-code store; install as app/hr_sso_store.py in stuff.

SQLite lives beside the application database, not inside the business schema.
Tokens are random opaque values; only their SHA-256 hashes are stored here.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


class InvalidGrant(ValueError):
    pass


class Store:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS hr_grants (hash TEXT PRIMARY KEY, kind TEXT NOT NULL, expires INTEGER NOT NULL, payload TEXT NOT NULL)')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            with c:
                yield c
        finally:
            c.close()

    def authorize(self, uid, session_version, redirect_uri, code_challenge):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', code_challenge):
            raise InvalidGrant('S256 challenge required')
        code = secrets.token_urlsafe(32)
        payload = dict(uid=uid, version=session_version or '', redirect_uri=redirect_uri,
                       challenge=code_challenge)
        with self.connection() as c:
            c.execute('DELETE FROM hr_grants WHERE expires <= ?', (int(self.clock()),))
            c.execute('INSERT INTO hr_grants VALUES (?,?,?,?)',
                      (token_hash(code), 'code', int(self.clock()) + 60, json.dumps(payload)))
        return code

    def exchange(self, code, verifier, redirect_uri):
        if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier):
            raise InvalidGrant('Invalid verifier')
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT expires,payload FROM hr_grants WHERE hash=? AND kind=?',
                            (token_hash(code), 'code')).fetchone()
            if not row or row[0] <= self.clock():
                raise InvalidGrant('Expired or consumed code')
            payload = json.loads(row[1])
            if payload['redirect_uri'] != redirect_uri or not secrets.compare_digest(payload['challenge'], challenge(verifier)):
                raise InvalidGrant('Code binding mismatch')
            c.execute('DELETE FROM hr_grants WHERE hash=?', (token_hash(code),))
            token = secrets.token_urlsafe(32)
            c.execute('INSERT INTO hr_grants VALUES (?,?,?,?)',
                      (token_hash(token), 'access', int(self.clock()) + 8 * 3600, json.dumps(payload)))
        return token

    def lookup(self, token):
        with self.connection() as c:
            row = c.execute('SELECT expires,payload FROM hr_grants WHERE hash=? AND kind=?',
                            (token_hash(token), 'access')).fetchone()
        if not row or row[0] <= self.clock():
            return None
        return json.loads(row[1])

    def revoke(self, token):
        with self.connection() as c:
            c.execute('DELETE FROM hr_grants WHERE hash=? AND kind=?', (token_hash(token), 'access'))
