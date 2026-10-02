# Read-only business pilot

The pilot UI now exposes employee profiles, contracts/documents, leave balances and
requests, and raw attendance/work records. All business reads use `mode=ro` plus
`PRAGMA query_only`; no application route creates, edits or approves HR records.
Existing stuff remains the writer. Pilot data is an imported snapshot, not live sync.

## Prepare private data

1. Export a consistent HR bundle and import a NEW HR database using the README commands.
2. Copy referenced attachments with `python -m hr.attachments`. Map every original
   storage prefix to its private backup root using repeated `--root original=backup`.
   Only original references are copied: employee scans, resumes, leave proofs, contract
   variants and company signature image. Referenced missing files, unmapped roots,
   symlink escapes or original hash mismatch abort without publishing a partial bundle.
3. Install `hr.db` and `files/` inside the private HR data volume, owned by UID 10001.
   Do not mount stuff's writable database or expose a public files/static directory.
4. Configure identities/permissions and SSO per `sso.md`; use masked data in developer
   environments. Live data must never be pushed to GitHub.

## Read permissions

Every authenticated user can read their own records only. An unlinked account is denied
self views; it does not mean “all employees.” Additional read grants are explicit stuff
User IDs:

- `HR_PROFILE_SUBJECTS`: other employees' personal/employment/bank records.
- `HR_LEAVE_SUBJECTS`: other employees' leave proofs, balances and attendance records.
- `HR_DOCUMENT_SUBJECTS`: other employees' assigned documents and download variants.
- `HR_ADMIN_SUBJECTS`: all three categories; HR-only, never a stuff permission change.

A directory visible to any HR reader contains ID/name/status/job only, never bank,
phone or identity-document details. Employee and record IDs from the browser are not
trusted; each request and each download checks the owning employee. Downloads require
an explicit source-path mapping, root containment and checksum verification.

## Limitations before full cutover

- No profile editing, leave submission/approval, template publishing, OTP signing,
  recruitment operations or salary computation UI yet.
- Online presence is not approved attendance and cannot alone determine payroll.
- Snapshot data is not automatically current. Final production cutover requires final
  delta transfer and preventing old stuff writes for each transferred module.
- Existing append-only evidence is preserved; the pilot performs no sign/confirm state
  transitions. Download audit logging and permission management UI remain prerequisites
  for operating the final document module.
- Original schema/version-1 importer is required. Missing/unexpected database returns a
  service-unavailable error rather than silently generating an empty database.

Validation: module authorization, cross-employee access, separately scoped HR permissions,
path traversal, symlink escape, content tampering, pagination and missing DB behavior are
covered by tests. Browser walkthrough uses synthetic records only.
