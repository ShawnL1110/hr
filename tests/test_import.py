from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from sqlalchemy import create_engine
from hr.models import Base
from hr.migration import export
from hr.import_bundle import load


class ImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root/'source.db'
        engine = create_engine('sqlite:///'+str(self.source))
        Base.metadata.create_all(engine)
        engine.dispose()
        with closing(sqlite3.connect(self.source)) as c, c:
            c.execute("INSERT INTO employee(id,name) VALUES (42,'Fixture employee')")
            c.execute("INSERT INTO user(id,username,employee_id,status) VALUES (7,'fixture',42,'active')")

    def test_roundtrip_ids_and_no_password_schema(self):
        export(self.source, self.root/'bundle')
        result = load(self.root/'bundle', self.root/'hr.db')
        self.assertFalse(result['business_cutover'])
        with closing(sqlite3.connect(self.root/'hr.db')) as c:
            self.assertEqual((7,42), c.execute('SELECT id,employee_id FROM user').fetchone())
            self.assertNotIn('password_hash', [r[1] for r in c.execute('PRAGMA table_info(user)')])
            self.assertEqual([], list(c.execute('PRAGMA foreign_key_check')))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            load(self.root/'bundle', self.root/'hr.db')

    def test_orphan_aborts_without_publishing(self):
        with closing(sqlite3.connect(self.source)) as c, c:
            c.execute('UPDATE user SET employee_id=999')
        export(self.source, self.root/'bundle')
        with self.assertRaisesRegex(ValueError, 'Foreign-key'):
            load(self.root/'bundle', self.root/'hr.db')
        self.assertFalse((self.root/'hr.db').exists())
        self.assertEqual([], list(self.root.glob('.hr-import-*')))
