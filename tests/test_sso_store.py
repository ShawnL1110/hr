from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('hr_sso_store', Path(__file__).resolve().parents[1]/'integrations/stuff/hr_sso_store.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.store = m.Store(Path(self.temp.name)/'tokens.db', lambda: self.now)
        self.verifier = 'a' * 43
        self.uri = 'https://hr.newtonfin.com/auth/callback'

    def code(self):
        return self.store.authorize(7, 'v1', self.uri, m.challenge(self.verifier))

    def test_exchange_one_use_and_revoke(self):
        code = self.code()
        token = self.store.exchange(code, self.verifier, self.uri)
        self.assertEqual(7, self.store.lookup(token)['uid'])
        with self.assertRaises(m.InvalidGrant):
            self.store.exchange(code, self.verifier, self.uri)
        self.store.revoke(token)
        self.assertIsNone(self.store.lookup(token))

    def test_bindings(self):
        code = self.code()
        for verifier, uri in [('b'*43, self.uri), (self.verifier, self.uri+'evil')]:
            with self.assertRaises(m.InvalidGrant):
                self.store.exchange(code, verifier, uri)
        self.assertIsNotNone(self.store.exchange(code, self.verifier, self.uri))

    def test_expiry(self):
        code = self.code()
        self.now += 60
        with self.assertRaises(m.InvalidGrant):
            self.store.exchange(code, self.verifier, self.uri)
        token = self.store.exchange(self.code(), self.verifier, self.uri)
        self.now += 28800
        self.assertIsNone(self.store.lookup(token))

    def test_concurrent_redemption_exactly_once(self):
        code = self.code()
        def exchange(_):
            try:
                return self.store.exchange(code, self.verifier, self.uri)
            except m.InvalidGrant:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(exchange, range(8)))
        self.assertEqual(1, sum(bool(r) for r in results))

    def test_raw_tokens_not_stored(self):
        code = self.code()
        self.assertNotIn(code.encode(), self.store.path.read_bytes())
        token = self.store.exchange(code, self.verifier, self.uri)
        self.assertNotIn(token.encode(), self.store.path.read_bytes())
