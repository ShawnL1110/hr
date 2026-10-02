# Newton HR

Independent HR service for `hr.newtonfin.com`, extracted in stages from stuff.

**Status: migration foundation; not a production replacement.** Personnel, contracts,
recruitment, leave and payroll still run in stuff. This repository currently contains
an independent service with tested SSO client/provider integration, HR export tooling,
source inventory, independent data models/importer, the extracted leave engine, and payroll reconciliation tooling. No production cutover has occurred.

## Run and test

Python 3.12+. Install `requirements.txt`, configure `.env` from `.env.example` with
an independently generated dedicated SSO client credential, then:

```sh
python -m unittest discover -s tests -v
docker compose build hr-app
docker compose up -d hr-app
```

Compose reads `.env`; direct `uvicorn hr.main:create_app --factory` requires environment
variables exported by the operator. Browser authentication requires the HTTPS HR domain
and the matching stuff integration; a health check alone is not a successful integration.

## Ownership

| HR owns after cutover | stuff continues owning |
|---|---|
| Employee employment, personal and bank records | Login accounts, credentials and account lifecycle |
| Contracts, original PDFs, receipts, signature audit | Collection assignments and business teams |
| Recruiting, candidates, candidate communications | Customer conversations and collection facts |
| Leave, approved attendance, salary policies and payroll | Raw work activity, quality facts, recovered amounts/counts |
| Frozen payslips and labor cost outputs | ROI consumer of HR labor-cost API |

No shared writable database, source password copies or shared browser cookie. HR role
assignment is separate from stuff roles. HR developers receive only this repository and
masked test data, not stuff production credentials or original customer data.

## Migration tools

Use a private SQLite backup and an operator-only output directory. Never commit exports.

```sh
python -m hr.migration export --source /private/backup/collection.db --destination private/bundle
python -m hr.migration verify private/bundle
python -m hr.import_bundle private/bundle --destination private/hr.db
python tools/capture_payroll_baseline.py --source-repo /path/to/stuff --source-backup /private/backup/collection.db --week 2026-09-21 --output private/baseline.json
python -m hr.reconcile private/baseline.json private/hr-calculation.json
```

The baseline tool runs with the existing stuff Python environment. It copies the backup
into a disposable scratch database; it does not import the stuff application entry point.
Exports contain HR PII and need encrypted transport/storage. Source DB is opened read-only,
all tables use one consistent read transaction, output uses explicit allowlists, original
IDs, restrictive file permissions, hashes and row counts. Active signature OTPs are
invalidated; historical signing audit and assignments remain. Unknown HR columns stop
export instead of silently losing data. The importer creates a new isolated database, checks every foreign key and refuses overwrite.
Attachment transfer and production migration rehearsal remain pending.

See [implementation status](docs/implementation.md) and [SSO integration](docs/sso.md).
