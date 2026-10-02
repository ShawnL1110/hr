import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from hr.migration import export, verify, PROJECTIONS


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/'source.db'
        self.inventory = self.root/'inventory.json'
        self.inventory.write_text(json.dumps({'tables': [
            {'table': 'employee', 'columns': ['id', 'name']},
            {'table': 'empdoc_otp', 'columns': ['id', 'code', 'locked']},
        ]}))
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('CREATE TABLE employee(id INTEGER PRIMARY KEY, name TEXT)')
            c.execute("INSERT INTO employee VALUES (7,'Test')")
            c.execute('CREATE TABLE empdoc_otp(id INTEGER PRIMARY KEY, code TEXT, locked INTEGER)')
            c.execute("INSERT INTO empdoc_otp VALUES (1,'123456',0)")
            for table, cols in PROJECTIONS.items():
                definitions = ','.join('"'+col+'" '+('INTEGER PRIMARY KEY' if col=='id' else 'TEXT') for col in cols)
                c.execute('CREATE TABLE "'+table+'" ('+definitions+')')
            c.execute('ALTER TABLE user ADD COLUMN password_hash TEXT')
            c.execute("INSERT INTO user (id,username,password_hash) VALUES (1,'test','SECRET')")
            c.execute('CREATE TABLE customer_secret(value TEXT)')
            c.execute("INSERT INTO customer_secret VALUES ('PRIVATE')")

    def run_export(self):
        return export(self.db, self.root/'bundle', self.inventory)

    def test_allowlist_source_unchanged_and_otp_invalidated(self):
        before = self.db.read_bytes()
        self.run_export()
        self.assertEqual(before, self.db.read_bytes())
        bundle = self.root/'bundle'
        self.assertNotIn('password_hash', (bundle/'user.jsonl').read_text())
        self.assertFalse((bundle/'customer_secret.jsonl').exists())
        otp = json.loads((bundle/'empdoc_otp.jsonl').read_text())
        self.assertIsNone(otp['code'])
        self.assertEqual(1, otp['locked'])
        self.assertEqual(1, verify(bundle)['employee'])
        self.assertEqual(0o600, (bundle/'employee.jsonl').stat().st_mode & 0o777)

    def test_schema_drift_fails_without_partial_bundle(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('ALTER TABLE employee ADD COLUMN unexpected TEXT')
        with self.assertRaisesRegex(ValueError, 'Schema drift'):
            self.run_export()
        self.assertFalse((self.root/'bundle').exists())
        self.assertEqual([], list(self.root.glob('.hr-export-*')))

    def test_refuse_overwrite(self):
        self.run_export()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_export()

    def test_tampering_detected(self):
        self.run_export()
        (self.root/'bundle/employee.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            verify(self.root/'bundle')

    def test_missing_table_blocks_export(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TABLE empdoc_otp')
        with self.assertRaisesRegex(ValueError, 'Missing required'):
            self.run_export()
