from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from hr.models import Base
from hr.portal import register


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        engine = create_engine('sqlite:///'+str(self.root/'hr.db'))
        Base.metadata.create_all(engine)
        engine.dispose()
        with closing(sqlite3.connect(self.root/'hr.db')) as c, c:
            c.execute('CREATE TABLE hr_schema_version(version INTEGER)')
            c.execute('INSERT INTO hr_schema_version VALUES (1)')
            c.execute("INSERT INTO employee(id,name,bank_iban) VALUES (1,'One','PRIVATE1'),(2,'Two','PRIVATE2')")
            c.execute("INSERT INTO leave_type(id,code,name_zh,unit) VALUES (1,'VAC','假期','day')")
            c.execute("INSERT INTO leave_request(id,employee_id,leave_type_id,date_from,date_to,proof_path) VALUES (1,1,1,'2026-10-01','2026-10-02','/legacy/a.pdf'),(2,2,1,'2026-10-01','2026-10-02','/legacy/a.pdf')")
            c.execute("INSERT INTO attendance_log(employee_id,day) VALUES (1,'2026-10-01'),(2,'2026-10-01')")
            c.execute("INSERT INTO empdoc_file(id,name,pdf_path) VALUES (1,'Contract','/legacy/a.pdf')")
            c.execute("INSERT INTO empdoc_assignment(id,employee_id,file_id) VALUES (1,1,1),(2,2,1)")
        files = self.root/'files'
        files.mkdir()
        (files/'a.pdf').write_bytes(b'%PDF-1.4 fixture')
        self.entry = {'path':'a.pdf','sha256':hashlib.sha256((files/'a.pdf').read_bytes()).hexdigest()}
        self.write_manifest()
        self.identity = {'sub':'9','employee_id':1,'permissions':[]}
        async def current(request): return self.identity, {}
        app = FastAPI()
        register(app,current,{'HR_DATA_DIR':str(self.root)})
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def write_manifest(self):
        (self.root/'files/manifest.json').write_text(json.dumps({'files':{'/legacy/a.pdf':self.entry}}))

    def test_employee_cannot_read_other_employee_across_modules(self):
        urls=['/api/profile?employee_id=2','/api/leave?employee_id=2','/api/documents?employee_id=2',
              '/api/attendance?employee_id=2&date_from=2026-10-01&date_to=2026-10-02',
              '/api/documents/2/download','/api/leave/2/proof','/api/employees']
        for url in urls:
            with self.subTest(url=url): self.assertEqual(403,self.client.get(url).status_code)

    def test_own_profile_and_history_readonly(self):
        before=(self.root/'hr.db').read_bytes()
        self.assertEqual('PRIVATE1',self.client.get('/api/profile').json()['bank_iban'])
        self.assertEqual([1],[r['id'] for r in self.client.get('/api/leave').json()['items']])
        self.assertEqual([1],[r['id'] for r in self.client.get('/api/documents').json()['items']])
        self.assertEqual(before,(self.root/'hr.db').read_bytes())

    def test_permissions_are_separate(self):
        self.identity['permissions']=['documents.read_all']
        self.assertEqual(200,self.client.get('/api/documents?employee_id=2').status_code)
        self.assertEqual(403,self.client.get('/api/profile?employee_id=2').status_code)
        listing=self.client.get('/api/employees').json()
        self.assertNotIn('bank_iban',listing['items'][0])
        self.assertEqual(403,self.client.get('/api/leave?employee_id=2').status_code)

    def test_unlinked_account_does_not_default_to_all(self):
        self.identity['employee_id']=None
        self.assertEqual(403,self.client.get('/api/profile').status_code)
        self.assertEqual(403,self.client.get('/api/documents').status_code)

    def test_download_shared_original_with_attachment_header(self):
        r=self.client.get('/api/documents/1/download')
        self.assertEqual(200,r.status_code)
        self.assertTrue(r.headers['content-disposition'].startswith('attachment;'))
        self.assertEqual(b'%PDF-1.4 fixture',r.content)

    def test_tamper_and_path_escape_rejected(self):
        (self.root/'files/a.pdf').write_bytes(b'tampered')
        self.assertEqual(404,self.client.get('/api/documents/1/download').status_code)
        self.entry['path']='../hr.db'; self.write_manifest()
        self.assertEqual(404,self.client.get('/api/documents/1/download').status_code)

    def test_symlink_escape_rejected(self):
        (self.root/'files/link').symlink_to(self.root/'hr.db')
        self.entry['path']='link'; self.write_manifest()
        self.assertEqual(404,self.client.get('/api/documents/1/download').status_code)

    def test_date_range_and_pagination(self):
        self.assertEqual(400,self.client.get('/api/attendance?date_from=2026-10-02&date_to=2026-10-01').status_code)
        self.assertEqual(422,self.client.get('/api/documents?limit=999').status_code)
        self.identity['permissions']=['profile.read_all']
        response=self.client.get('/api/employees?offset=1&limit=1').json()
        self.assertEqual(2,response['total']); self.assertEqual(2,response['items'][0]['id'])

    def test_missing_db_does_not_create_empty_database(self):
        (self.root/'hr.db').unlink()
        self.assertEqual(503,self.client.get('/api/profile').status_code)
        self.assertFalse((self.root/'hr.db').exists())
