import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from fastapi import FastAPI
from fastapi.testclient import TestClient


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.user = types.SimpleNamespace(id=7, username='fixture', status='active', sess_token='v1', employee_id=42)
        self.employee = types.SimpleNamespace(status='active')
        self.logged_in = True
        package = types.ModuleType('hr_test_provider')
        package.__path__ = []
        package.auth = types.SimpleNamespace(current_user=lambda request: self.user if self.logged_in else None)
        package.models = types.SimpleNamespace(User=object(), Employee=object())
        owner = self
        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, model, uid):
                return owner.user if model is package.models.User else owner.employee
        package.db = types.SimpleNamespace(SessionLocal=Session)
        modules = {'hr_test_provider': package}
        root = Path(__file__).resolve().parents[1]/'integrations/stuff'
        for name in ('hr_sso_store', 'hr_sso'):
            spec = importlib.util.spec_from_file_location('hr_test_provider.'+name, root/(name+'.py'))
            module = importlib.util.module_from_spec(spec)
            modules[spec.name] = module
            with patch.dict(sys.modules, modules):
                spec.loader.exec_module(module)
        self.store_module = modules['hr_test_provider.hr_sso_store']
        app = FastAPI()
        self.secret = 'x'*64
        self.callback = 'https://hr.newtonfin.com/auth/callback'
        with patch.dict(os.environ, {'HR_SSO_ENABLED':'1', 'HR_SSO_CALLBACK':self.callback, 'HR_SSO_STORE': self.tmp.name+'/sso.db', 'HR_SSO_CLIENT_SECRET':self.secret}):
            modules['hr_test_provider.hr_sso'].register(app)
        self.client = TestClient(app, base_url='https://stuff.newtonfin.com', follow_redirects=False)
        self.addCleanup(self.client.close)
        self.verifier = 'a'*43

    def authorize(self, **overrides):
        params = dict(client_id='newton-hr', redirect_uri=self.callback, state='s'*43,
                      code_challenge=self.store_module.challenge(self.verifier), code_challenge_method='S256', response_type='code')
        params.update(overrides)
        return self.client.get('/api/hr-sso/authorize', params=params)

    def post(self, route, data):
        return self.client.post('/api/hr-sso/'+route, json=data, headers={'Authorization':'Bearer '+self.secret})

    def token(self):
        r = self.authorize()
        code = parse_qs(urlsplit(r.headers['location']).query)['code'][0]
        r = self.post('token', dict(grant_type='authorization_code', client_id='newton-hr', redirect_uri=self.callback, code=code, code_verifier=self.verifier))
        self.assertEqual(200, r.status_code)
        return r.json()['access_token']

    def test_revalidate_password_version_and_employee_status(self):
        token = self.token()
        self.assertTrue(self.post('introspect', {'token':token}).json()['active'])
        self.user.sess_token = 'v2'
        self.assertFalse(self.post('introspect', {'token':token}).json()['active'])
        token = self.token()
        self.employee.status = 'inactive'
        self.assertFalse(self.post('introspect', {'token':token}).json()['active'])
        self.assertEqual(403, self.authorize().status_code)

    def test_exact_redirect_and_client_auth(self):
        self.assertEqual(400, self.authorize(redirect_uri=self.callback+'?evil=1').status_code)
        self.assertEqual(401, self.client.post('/api/hr-sso/introspect', json={'token':'x'}).status_code)
        self.assertEqual(400, self.post('token', []).status_code)

    def test_unauthenticated_redirects_to_stuff_login(self):
        self.logged_in = False
        r = self.authorize()
        self.assertEqual(302, r.status_code)
        self.assertTrue(r.headers['location'].startswith('/login?next='))

    def test_authorize_and_exchange_are_rate_limited(self):
        for _ in range(120):
            self.assertEqual(302,self.authorize().status_code)
        self.assertEqual(429,self.authorize().status_code)
        for _ in range(120):
            r=self.client.post('/api/hr-sso/token',json={})
            self.assertEqual(401,r.status_code)
        self.assertEqual(429,self.client.post('/api/hr-sso/token',json={}).status_code)
