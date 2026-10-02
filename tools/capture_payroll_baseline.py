#!/usr/bin/env python3
"""Capture the legacy calculator against a disposable COPY of a SQLite backup.

Does not import app.main, run seed jobs, connect to production, or mutate the backup.
Run with the stuff Python environment. Output contains salaries/employee PII.
"""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-repo', type=Path, required=True)
    p.add_argument('--source-backup', type=Path, required=True)
    p.add_argument('--week', type=dt.date.fromisoformat, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    from zoneinfo import ZoneInfo
    today = dt.datetime.now(ZoneInfo('Europe/Madrid')).date()
    if args.week.weekday() != 0 or args.week + dt.timedelta(days=5) >= today:
        p.error('--week must be the Monday of a completed payroll week')
    if args.output.exists():
        p.error('Refusing to overwrite baseline')
    source = args.source_repo.resolve()
    backup = args.source_backup.resolve()
    if not (source/'app/payroll.py').is_file() or not backup.is_file():
        p.error('Source repository or backup missing')
    with tempfile.TemporaryDirectory(prefix='hr-payroll-baseline-') as temp:
        scratch = Path(temp)/'baseline.db'
        with closing(sqlite3.connect(backup.as_uri()+'?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(scratch)) as dst:
                src.backup(dst)
        # db.py imports only these settings; never load the source .env/main.py.
        os.environ['DB_URL'] = 'sqlite:///'+str(scratch)
        os.environ['TZ'] = 'Europe/Madrid'
        import time
        if hasattr(time, 'tzset'):
            time.tzset()
        sys.path.insert(0, str(source))
        from app import db, payroll
        hashes = {str(f.relative_to(source)): hashlib.sha256(f.read_bytes()).hexdigest()
                  for f in sorted((source/'app').glob('*.py'))}
        with db.SessionLocal() as session:
            slips = payroll.weekly_all(session, args.week)
        result = {'format': 'newton-hr-payroll-baseline/v1', 'week': args.week.isoformat(),
                  'calculated_on': today.isoformat(), 'source_sha256': hashes,
                  'employees': len(slips), 'slips': slips}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        db.engine.dispose()
        print(json.dumps({'week': args.week.isoformat(), 'employees': len(slips)}))


if __name__ == '__main__':
    main()
