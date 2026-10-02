from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from sqlalchemy import create_engine
from hr.models import Base
from hr.migration import export
from hr.attachments import copy_bundle


class AttachmentsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.backup=self.root/'backup'; self.backup.mkdir()
        (self.backup/'a.pdf').write_bytes(b'%PDF fixture')
        (self.backup/'customer.pdf').write_bytes(b'customer must not be copied')
        self.sha=hashlib.sha256((self.backup/'a.pdf').read_bytes()).hexdigest()
        db=self.root/'source.db'; engine=create_engine('sqlite:///'+str(db)); Base.metadata.create_all(engine); engine.dispose()
        with closing(sqlite3.connect(db)) as c,c:
            c.execute('INSERT INTO empdoc_file(id,pdf_path,sha256) VALUES (1,?,?)',('/data/proofs/a.pdf',self.sha))
        export(db,self.root/'bundle')

    def copy(self):
        return copy_bundle(self.root/'bundle',self.root/'files',[('/data/proofs',self.backup)])

    def test_only_referenced_files_copied(self):
        result=self.copy()
        self.assertEqual(1,result['files'])
        self.assertEqual([self.sha+'.pdf','manifest.json'],sorted(p.name for p in (self.root/'files').iterdir()))
        with self.assertRaises(ValueError): self.copy()

    def test_original_checksum_mismatch_stops_publication(self):
        (self.backup/'a.pdf').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'): self.copy()
        self.assertFalse((self.root/'files').exists())
        self.assertEqual([],list(self.root.glob('.hr-files-*')))

    def test_symlink_escape_stops_copy(self):
        outside=self.root/'outside.pdf'; outside.write_bytes(b'%PDF fixture')
        (self.backup/'a.pdf').unlink(); (self.backup/'a.pdf').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'escapes'): self.copy()

    def test_missing_root_stops_copy(self):
        with self.assertRaisesRegex(ValueError,'mapped backup root'):
            copy_bundle(self.root/'bundle',self.root/'files',[('/other',self.backup)])
