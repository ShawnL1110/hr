"""Independent HR service. Business cutover remains disabled during migration."""
import base64
import hashlib
from html import escape
import os
from pathlib import Path
import secrets
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from .session import Sessions

COOKIE = '__Host-hr-session'
LOGIN_COOKIE = '__Host-hr-login'


def create_app(settings=None, transport=None):
    settings = settings if settings is not None else os.environ
    origin = settings.get('HR_ORIGIN', 'https://hr.newtonfin.com')
    issuer = settings.get('STUFF_ORIGIN', 'https://stuff.newtonfin.com')
    if origin != 'https://hr.newtonfin.com' or issuer != 'https://stuff.newtonfin.com':
        raise ValueError('Unexpected HR/stuff origin')
    secret = settings.get('HR_SSO_CLIENT_SECRET', '')
    if len(secret) < 32:
        raise ValueError('Configure a random HR_SSO_CLIENT_SECRET of at least 32 characters')
    admins = {x.strip() for x in settings.get('HR_ADMIN_SUBJECTS', '').split(',') if x.strip()}
    sessions = Sessions(Path(settings.get('HR_DATA_DIR', './data'))/'sessions.db')
    callback = origin + '/auth/callback'
    app = FastAPI(title='Newton HR', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        return response

    def cookie(response, name, value, ttl):
        response.set_cookie(name, value, max_age=ttl, secure=True, httponly=True, samesite='lax', path='/')

    async def backchannel(route, payload):
        try:
            async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=False) as client:
                response = await client.post(issuer+'/api/hr-sso/'+route,
                    headers={'Authorization': 'Bearer '+secret}, json=payload)
                if response.status_code in (400, 401, 403):
                    raise HTTPException(401, '请重新从 stuff 登录')
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError('Invalid identity response')
                return result
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, '暂时无法验证 stuff 账号，请稍后重试')

    async def current(request):
        session = sessions.get(request.cookies.get(COOKIE), 'session')
        if not session:
            raise HTTPException(401, '请从 stuff 登录')
        identity = await backchannel('introspect', {'token': session['token']})
        if identity.get('active') is not True:
            sessions.delete(request.cookies.get(COOKIE))
            raise HTTPException(401, '账号已停用或会话已过期')
        if not isinstance(identity.get('sub'), str) or not isinstance(identity.get('username'), str):
            raise HTTPException(503, '身份响应不完整')
        identity['hr_admin'] = identity['sub'] in admins
        return identity, session

    @app.get('/healthz')
    def health():
        return {'ok': True, 'service': 'hr', 'phase': 'integration', 'business_cutover': False}

    @app.get('/login')
    def login():
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        handle = sessions.put('login', {'state': state, 'verifier': verifier}, 300)
        url = issuer+'/api/hr-sso/authorize?'+urlencode({'client_id': 'newton-hr',
            'redirect_uri': callback, 'state': state, 'code_challenge': challenge,
            'code_challenge_method': 'S256', 'response_type': 'code'})
        response = RedirectResponse(url, status_code=302)
        cookie(response, LOGIN_COOKIE, handle, 300)
        return response

    @app.get('/auth/callback')
    async def callback_route(request: Request, code: str, state: str):
        pending = sessions.get(request.cookies.get(LOGIN_COOKIE), 'login', consume=True)
        if not pending or len(state) > 128 or len(code) > 256 or not secrets.compare_digest(pending['state'].encode(), state.encode()):
            raise HTTPException(400, '登录请求已失效，请重新登录')
        tokens = await backchannel('token', {'client_id': 'newton-hr', 'grant_type': 'authorization_code',
            'redirect_uri': callback, 'code': code, 'code_verifier': pending['verifier']})
        token = tokens.get('access_token')
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            raise HTTPException(503, '身份响应不完整')
        sessions.delete(request.cookies.get(COOKIE))
        handle = sessions.put('session', {'token': token, 'csrf': secrets.token_urlsafe(32)}, 28800)
        response = RedirectResponse('/', status_code=303)
        response.delete_cookie(LOGIN_COOKIE, path='/', secure=True, httponly=True, samesite='lax')
        cookie(response, COOKIE, handle, 28800)
        return response

    @app.get('/api/me')
    async def me(request: Request):
        identity, _ = await current(request)
        return identity

    @app.get('/')
    async def home(request: Request):
        if not sessions.get(request.cookies.get(COOKIE), 'session'):
            return RedirectResponse('/login', status_code=302)
        identity, session = await current(request)
        return HTMLResponse('<!doctype html><html lang="zh"><meta charset="utf-8"><title>Newton HR</title>'
            '<h1>Newton HR</h1><p>'+escape(identity['username'])+'，欢迎。</p>'
            '<p>HR 独立站正在迁移验证，现阶段请继续在 stuff 办理人事业务。</p>'
            '<p><a href="https://stuff.newtonfin.com">返回 stuff</a></p>'
            '<form method="post" action="/logout"><input type="hidden" name="csrf" value="'+escape(session['csrf'])+'">'
            '<button>退出 HR</button></form></html>')

    @app.post('/logout')
    async def logout(request: Request):
        # Logout checks origin and CSRF, and deletes locally even if issuer is unavailable.
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Invalid origin')
        from urllib.parse import parse_qs
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2048:
                raise HTTPException(400, 'Invalid form')
        try:
            fields = parse_qs(body.decode())
        except UnicodeDecodeError:
            raise HTTPException(400, 'Invalid form')
        session = sessions.get(request.cookies.get(COOKIE), 'session')
        if not session or not secrets.compare_digest(session['csrf'].encode(), fields.get('csrf', [''])[0].encode()):
            raise HTTPException(403, 'Invalid CSRF token')
        sessions.delete(request.cookies.get(COOKIE))
        try:
            await backchannel('revoke', {'token': session['token']})
        except HTTPException:
            pass
        response = RedirectResponse('/login', status_code=303)
        response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='lax')
        return response

    return app
