from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
import httpx
from fastapi.testclient import TestClient
from hr.main import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.active = True
        self.calls = []
        def issuer(request):
            self.calls.append(request.url.path)
            if request.url.path.endswith('/token'):
                return httpx.Response(200, json={'access_token': 'T'*43})
            if request.url.path.endswith('/introspect'):
                return httpx.Response(200, json={'active': self.active, 'sub': '7', 'username': 'Test', 'employee_id': 42})
            return httpx.Response(200, json={'ok': True})
        app = create_app({'HR_DATA_DIR': temp.name, 'HR_SSO_CLIENT_SECRET': 'x'*64}, httpx.MockTransport(issuer))
        self.client = TestClient(app, base_url='https://hr.newtonfin.com', follow_redirects=False)
        self.addCleanup(self.client.close)

    def login(self):
        response = self.client.get('/login')
        query = parse_qs(urlsplit(response.headers['location']).query)
        response = self.client.get('/auth/callback', params={'code': 'code', 'state': query['state'][0]})
        self.assertEqual(303, response.status_code)
        return query

    def test_login_and_disable(self):
        self.login()
        r = self.client.get('/api/me')
        self.assertEqual(42, r.json()['employee_id'])
        self.assertFalse(r.json()['hr_admin'])
        self.active = False
        self.assertEqual(401, self.client.get('/api/me').status_code)
        self.assertEqual(401, self.client.get('/api/me').status_code)

    def test_state_binding_blocks_token_call(self):
        self.client.get('/login')
        self.assertEqual(400, self.client.get('/auth/callback?code=c&state=wrong').status_code)
        self.assertEqual([], self.calls)

    def test_callback_replay_blocked(self):
        q = self.login()
        self.assertEqual(400, self.client.get('/auth/callback', params={'code': 'code', 'state': q['state'][0]}).status_code)
        self.assertEqual(1, self.calls.count('/api/hr-sso/token'))

    def test_cookie_security_and_no_token_in_cookie(self):
        self.login()
        cookie = self.client.cookies.get('__Host-hr-session')
        self.assertNotIn('T'*43, cookie)
        r = self.client.get('/login')
        header = r.headers['set-cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=lax', 'Path=/'):
            self.assertIn(flag, header)
        self.assertNotIn('Domain=', header)

    def test_logout_csrf_and_revocation(self):
        self.login()
        self.assertEqual(403, self.client.post('/logout', data={'csrf': 'bad'}).status_code)
        html = self.client.get('/').text
        csrf = html.split('name="csrf" value="')[1].split('"')[0]
        r = self.client.post('/logout', data={'csrf': csrf}, headers={'Origin': 'https://hr.newtonfin.com'})
        self.assertEqual(303, r.status_code)
        self.assertEqual(401, self.client.get('/api/me').status_code)
        self.assertIn('/api/hr-sso/revoke', self.calls)

    def test_health_is_explicitly_not_cutover(self):
        self.assertFalse(self.client.get('/healthz').json()['business_cutover'])
