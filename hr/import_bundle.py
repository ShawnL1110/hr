"""Load a verified HR bundle into a NEW isolated SQLite database. No cutover writes."""
import argparse
import base64
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from sqlalchemy import create_engine
from .migration import verify, INVENTORY, PROJECTIONS, quote
from .models import Base


def load(bundle, destination):
    bundle, destination = Path(bundle), Path(destination).absolute()
    if destination.exists():
        raise ValueError('Refusing to overwrite HR database')
    verify(bundle)
    manifest = json.loads((bundle/'manifest.json').read_text())
    approved = {t['table']: t['columns'] for t in json.loads(INVENTORY.read_text())['tables']}
    approved.update(PROJECTIONS)
    if set(manifest['tables']) != set(approved):
        raise ValueError('Bundle does not match reviewed table allowlist')
    for table, columns in approved.items():
        if set(manifest['tables'][table]['columns']) != set(columns):
            raise ValueError('Unreviewed columns: '+table)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.hr-import-', suffix='.db', dir=destination.parent)
    os.close(fd)
    scratch = Path(name)
    try:
        engine = create_engine('sqlite:///'+str(scratch))
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()
        c = sqlite3.connect(scratch)
        try:
            with c:
                # Cyclic employee/team/user references are validated after complete load.
                for table, columns in approved.items():
                    sql = 'INSERT INTO '+quote(table)+' ('+','.join(map(quote, columns))+') VALUES ('+','.join('?' for _ in columns)+')'
                    with (bundle/(table+'.jsonl')).open() as f:
                        for line in f:
                            row = json.loads(line)
                            values = [row[k] for k in columns]
                            values = [base64.b64decode(v['$binary'], validate=True) if isinstance(v, dict) and set(v)=={'$binary'} else v for v in values]
                            c.execute(sql, values)
                errors = list(c.execute('PRAGMA foreign_key_check'))
                if errors:
                    raise ValueError('Foreign-key reconciliation failed: '+str([(r[0],r[2]) for r in errors[:20]]))
                if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('SQLite integrity check failed')
                c.execute('CREATE TABLE hr_schema_version(version INTEGER NOT NULL)')
                c.execute('INSERT INTO hr_schema_version VALUES (1)')
        finally:
            c.close()
        # Recheck uniqueness; hardlink publishes without ever replacing an existing file.
        os.link(scratch, destination)
        return {'tables': len(approved), 'schema_version': 1, 'business_cutover': False}
    finally:
        scratch.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path)
    p.add_argument('--destination', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(load(args.bundle, args.destination)))


if __name__ == '__main__':
    main()
