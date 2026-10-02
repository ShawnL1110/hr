# HR / stuff login integration

This is a narrowly scoped confidential-client authorization-code bridge, not a general
OIDC provider. Exact client ID `newton-hr`, exact HTTPS callback, S256 PKCE, random state,
60-second single-use codes, 8-hour opaque access tokens, no refresh tokens. HR cookies
are host-only, Secure, HttpOnly, SameSite=Lax; codes/tokens are never logged by the HR
app. Reverse-proxy access logs must omit callback query strings and Authorization headers.

## stuff installation (not yet installed or enabled)

1. Copy `integrations/stuff/hr_sso.py` and `hr_sso_store.py` into stuff `app/` in an isolated
   checkout. Review and commit them to the stuff repository before deployment.
2. Import and call `hr_sso.register(app)` after the existing SessionMiddleware is installed.
3. Configure `HR_SSO_ENABLED=1`, `HR_SSO_CALLBACK=https://hr.newtonfin.com/auth/callback`,
   `HR_SSO_STORE=/data/app/hr_sso.db`, and a dedicated random `HR_SSO_CLIENT_SECRET`.
4. Put the same **client credential** in HR's environment. This is not stuff's session
   signing secret and cannot mint a user grant without an active stuff login.
5. Add an employee navigation link to `https://hr.newtonfin.com/login` only after real
   account validation. Existing HR links remain operational until module cutovers.

Every HR authenticated request introspects the access token against current stuff User
status and session version. Password reset invalidation and inactive Employee status
are checked server-side. Failure to contact stuff fails closed. API returns subject,
username and employee ID only; no password hashes, role grants or business data.

HR administrators are explicitly configured as stuff User IDs in `HR_ADMIN_SUBJECTS`.
An empty list grants no administrators. A later audited HR permission editor must preserve
separate document publish, payroll confirm and profile permissions before module cutover.

## Acceptance before enabling

- Real employee/admin login, unlinked account behavior, disabled employee/user, password
  reset, logout, expired codes, concurrent redemption and wrong redirect tested.
- Browser cannot read HR session token; no shared parent-domain cookie.
- HR role change does not change stuff permissions.
- Proxy excludes sensitive query strings from logs; repeated authorize/token calls rate limited.
- Session stores and backups are private; expired grants pruned.
- DNS and TLS correct; provider disabled by default until deployment is configured.
