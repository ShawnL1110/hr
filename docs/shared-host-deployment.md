# Shared-host read-only pilot

User approved co-location with finance/stuff at 35.42.59.31. HR has its own
`hr-app` container, `/opt/hr` source directory and `hr_hr-data` volume. Only
Caddy publishes HTTPS. Runtime limits: 256 MiB memory, 384 MiB memory+swap,
0.5 CPU; non-root UID 10001, read-only root filesystem, no capabilities.

DNS: hr.newtonfin.com → 35.42.59.31. Caddy config source: deploy/hr.caddy.
HR grants are independent: owner account User 1 is explicitly configured as
HR administrator; all other users default to their own employee records.
No HR developer receives host root/Docker control, stuff credentials or source
customer data. A separate restricted deployment workflow is needed before
handing production publishing rights to another team.

2026-10-02 migration rehearsal:
- Consistent SQLite backup under /home/ubuntu/backup/hr-pilot-20261002/.
- Export allowlist: 32 tables; source remains authoritative, no cutover.
- Imported 40 employee records; SQLite integrity and foreign keys passed.
- One legacy daily_work_entry stored username `admin` in submitted_by.
  Explicit --resolve-legacy-audit-usernames maps it to existing User 1;
  hr_import_notes records original value and mapping. Source backup and export
  remain unchanged. Missing/ambiguous actors and other orphan relations still fail.
- 107 HR attachment references / 106 distinct files, all hashes verified.
- Freshness is a one-time snapshot, not an automatic live synchronization.

Private settings are stored in local .env and private/stuff-hr.env, mirrored to
server /opt/hr/.env and the HR_SSO_* entries in /opt/collection/.env when enabled.
Never copy stuff SECRET_KEY to HR. Dedicated client secret alone cannot grant
access without an authenticated, active stuff user. Provider codes are single-use,
PKCE-bound and expire after 60 seconds. Every HR request revalidates identity.

Code and form provider changes are committed to the stuff repository; apply its
`deploy/hr-sso-production.patch` only to a matching live baseline. Do not replace
live stuff main.py with the older Git main file. Back up image, source and .env
before enabling. Rebuild only collection; reload Caddy, never restart it.

Rollback: remove HR entry/disable HR_SSO_ENABLED and restore prior stuff image;
stop only hr-app and remove only hr.caddy after Caddy validation. Preserve private
HR snapshot and audit files. No HR business writes exist in this pilot.

## 2026-10-02 live deployment

User advanced deployment to approximately 13:06 Europe/Madrid. HR HTTPS /healthz
returns 200; stuff SSO is enabled and the global HR link is installed. Guest login
redirects correctly to stuff; unauthorized /api/me returns 401; the dedicated
live SSO backchannel is verified. The user explicitly assigned real account login
and business-page acceptance to the HR team; these are not reported as completed.
41 automated tests pass, including employee-scope and attachment authorization.
HR database integrity/foreign keys pass, with 40 employees in the imported snapshot.

HR is attached only to hr_frontend, alongside Caddy. Caddy's network attachment
is persisted in /opt/kyc/docker-compose.yml while preserving its default network;
Caddy was reloaded, not restarted. HR uses the root-owned fixed deployment policy
/etc/newton-hr-deploy/compose.json (not /opt/hr/compose.yaml), UID10001, private
hr_hr-data volume, read-only root, 256MiB memory and 0.5 CPU, no published port.
Backups: /home/ubuntu/backup/hr-live-20261002; stuff rollback image:
collection-rollback:before-hr-sso. Latest CS reply repair remains installed.
The original 14:00 scheduled deployment was paused to prevent duplicate execution.

HR team acceptance: authenticate via stuff and return to HR; verify owner/admin
and ordinary employee scopes; inspect profile, contract downloads, leave and
attendance against the snapshot. Report discrepancies with page/time and role,
without sharing credentials. Business writes and automatic synchronization remain
out of scope for this read-only pilot. Keep stuff as the authoritative writer.
