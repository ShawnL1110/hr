"""Feature-gated HR identity bridge; install alongside hr_sso_store in stuff app.

Wire register(app) after SessionMiddleware. Disabled unless HR_SSO_ENABLED=1.
No HR business data or password hashes are returned by this API.
"""
import json
import os
import re
import secrets
import logging
import threading
import time
from collections import OrderedDict
from urllib.parse import urlencode, urlsplit
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from . import auth, db, models
from .hr_sso_store import Store, InvalidGrant


def register(app):
    if os.getenv('HR_SSO_ENABLED') != '1':
        return
    callback = os.environ['HR_SSO_CALLBACK']
    client_secret = os.environ['HR_SSO_CLIENT_SECRET']
    parsed = urlsplit(callback)
    if parsed.scheme != 'https' or parsed.hostname != 'hr.newtonfin.com' or parsed.path != '/auth/callback' or parsed.query or parsed.fragment or parsed.username or parsed.port:
        raise ValueError('HR callback must be https://hr.newtonfin.com/auth/callback')
    if len(client_secret) < 32:
        raise ValueError('HR client secret must have at least 32 random characters')
    store = Store(os.environ['HR_SSO_STORE'])

    # Bound memory and auth-request frequency without logging codes/query strings.
    buckets = OrderedDict()
    limiter_lock = threading.Lock()
    def throttle(request, route):
        now = int(time.monotonic() // 60)
        key = (route, request.client.host if request.client else 'unknown')
        with limiter_lock:
            window, count = buckets.pop(key, (now, 0))
            count = count + 1 if window == now else 1
            buckets[key] = (now, count)
            while len(buckets) > 2048:
                buckets.popitem(last=False)
        if count > 120:
            raise HTTPException(429, 'Too many login requests', headers={'Retry-After': '60'})

    class SafeAccessLog(logging.Filter):
        def filter(self, record):
            args = record.args
            if isinstance(args, tuple) and len(args) == 5 and str(args[2]).startswith('/api/hr-sso/'):
                record.args = (*args[:2], str(args[2]).split('?', 1)[0], *args[3:])
            return True
    logging.getLogger('uvicorn.access').addFilter(SafeAccessLog())

    def client(request):
        expected = 'Bearer ' + client_secret
        if not secrets.compare_digest(request.headers.get('authorization', '').encode(), expected.encode()):
            raise HTTPException(401, 'Invalid HR client')

    async def payload(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(400, 'Request too large')
        try:
            value = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, 'Invalid JSON')
        if not isinstance(value, dict):
            raise HTTPException(400, 'Expected JSON object')
        return value

    def response(value):
        return JSONResponse(value, headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'})

    def principal(uid, version):
        with db.SessionLocal() as s:
            u = s.get(models.User, uid)
            if not u or u.status != 'active' or (u.sess_token or '') != version:
                return None
            e = s.get(models.Employee, u.employee_id) if u.employee_id else None
            if e and e.status != 'active':
                return None
            # HR grants are configured in HR. stuff administrator does not implicitly
            # become HR administrator, and HR cannot grant stuff permissions.
            return {'sub': str(u.id), 'username': u.username, 'employee_id': u.employee_id}

    @app.get('/api/hr-sso/authorize')
    def authorize(request: Request, client_id: str, redirect_uri: str, state: str,
                  code_challenge: str, code_challenge_method: str, response_type: str):
        throttle(request, 'authorize')
        if client_id != 'newton-hr' or redirect_uri != callback or response_type != 'code' or code_challenge_method != 'S256':
            raise HTTPException(400, 'Invalid authorization request')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', state):
            raise HTTPException(400, 'Invalid state')
        u = auth.current_user(request)
        if not u:
            next_path = request.url.path + '?' + request.url.query
            return RedirectResponse('/login?' + urlencode({'next': next_path}), status_code=302)
        if not principal(u.id, u.sess_token or ''):
            raise HTTPException(403, 'Inactive employee')
        try:
            code = store.authorize(u.id, u.sess_token, callback, code_challenge)
        except InvalidGrant:
            raise HTTPException(400, 'Invalid challenge')
        return RedirectResponse(callback + '?' + urlencode({'code': code, 'state': state}),
                                status_code=302, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

    @app.post('/api/hr-sso/token')
    async def token(request: Request):
        throttle(request, 'token')
        client(request)
        data = await payload(request)
        if data.get('grant_type') != 'authorization_code' or data.get('client_id') != 'newton-hr' or data.get('redirect_uri') != callback:
            raise HTTPException(400, 'Invalid token request')
        if any(not isinstance(data.get(k), str) or len(data[k]) > 256 for k in ('code', 'code_verifier')):
            raise HTTPException(400, 'Invalid token fields')
        try:
            value = store.exchange(data['code'], data['code_verifier'], callback)
        except InvalidGrant:
            raise HTTPException(400, 'Invalid grant')
        grant = store.lookup(value)
        if not grant or not principal(grant['uid'], grant['version']):
            store.revoke(value)
            raise HTTPException(401, 'Account changed')
        return response({'access_token': value, 'token_type': 'Bearer', 'expires_in': 28800})

    @app.post('/api/hr-sso/introspect')
    async def introspect(request: Request):
        client(request)
        data = await payload(request)
        value = data.get('token')
        if not isinstance(value, str) or len(value) > 256:
            raise HTTPException(400, 'Invalid token')
        grant = store.lookup(value)
        p = principal(grant['uid'], grant['version']) if grant else None
        return response(dict(active=True, **p) if p else {'active': False})

    @app.post('/api/hr-sso/revoke')
    async def revoke(request: Request):
        client(request)
        data = await payload(request)
        value = data.get('token')
        if not isinstance(value, str) or len(value) > 256:
            raise HTTPException(400, 'Invalid token')
        store.revoke(value)
        return response({'ok': True})
