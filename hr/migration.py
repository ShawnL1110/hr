"""Read-only, consistent HR export. Never export login secrets or customer tables.

Run against a SQLite backup, not a live cutover. The private bundle contains HR PII.
The source remains authoritative until reconciled application cutover.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone

INVENTORY = Path(__file__).resolve().parents[1] / 'docs/source-inventory.json'
PROJECTIONS = {
    'user': ('id', 'username', 'employee_id', 'status'),
    'team': ('id', 'name', 'leader_employee_id', 'institution'),
    'daily_work_entry': ('id', 'date', 'employee_id', 'present', 'qc_deduction', 'qc_items', 'wa_ok', 'daily_target_met', 'violation', 'note', 'submitted_by', 'created_at', 'updated_at'),
    'attendance_log': ('id', 'employee_id', 'day', 'first_at', 'last_at'),
}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def encoded(value):
    if isinstance(value, bytes):
        return {'$binary': base64.b64encode(value).decode('ascii')}
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def export(source, destination, inventory=INVENTORY):
    """Publish a complete bundle atomically; refuse overwrites and schema drift.

    No source DDL is executed. A single SQLite read transaction covers every table.
    Attached files are separately inventoried before cutover (not copied here).
    """
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_file():
        raise ValueError('Source backup does not exist')
    if destination.exists():
        raise ValueError('Destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    spec = json.loads(Path(inventory).read_text())
    tables = {t['table']: t for t in spec['tables']}
    stage = Path(tempfile.mkdtemp(prefix='.hr-export-', dir=destination.parent))
    os.chmod(stage, 0o700)
    db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        actual = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = set(tables) | set(PROJECTIONS)
        missing = expected - actual
        if missing:
            raise ValueError('Missing required tables: ' + ', '.join(sorted(missing)))
        manifest = {'format': 'newton-hr-export/v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                    'inventory_sha256': digest(Path(inventory)), 'tables': {},
                    'cutover_ready': False,
                    'pending': ['attachment reconciliation', 'payroll parity', 'identity mapping', 'single-writer cutover']}
        for table in sorted(expected):
            info = list(db.execute('PRAGMA table_info(' + quote(table) + ')'))
            columns = [r[1] for r in info]
            if table in tables:
                approved = tables[table]['columns']
                if set(columns) != set(approved):
                    raise ValueError('Schema drift: ' + table + '; review inventory before exporting')
                selected = approved
            else:
                # Facts may grow independently; projections require an explicit column list.
                selected = PROJECTIONS[table]
                if selected is None:
                    raise ValueError('Projection needs reviewed columns: ' + table)
                if not set(selected) <= set(columns):
                    raise ValueError('Projection schema mismatch: ' + table)
            order = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
            if not order:
                raise ValueError('Primary key required: ' + table)
            sql = 'SELECT ' + ','.join(map(quote, selected)) + ' FROM ' + quote(table)
            sql += ' ORDER BY ' + ','.join(map(quote, order))
            path = stage / (table + '.jsonl')
            count = 0
            with path.open('xb') as f:
                os.chmod(path, 0o600)
                for row in db.execute(sql):
                    record = dict(zip(selected, map(encoded, row)))
                    if table == 'empdoc_otp':
                        # Preserve attempts/audit context, never transfer a usable signing code.
                        record['code'] = None
                        record['locked'] = 1
                    f.write(canonical(record) + b'\n')
                    count += 1
            manifest['tables'][table] = {'rows': count, 'sha256': digest(path),
                                         'columns': list(selected), 'primary_key': order,
                                         'ownership': 'hr' if table in tables else 'stuff_projection'}
        db.rollback()
        manifest_path = stage / 'manifest.json'
        manifest_path.write_bytes(canonical(manifest) + b'\n')
        os.chmod(manifest_path, 0o600)
        # Rename to unique, nonexisting destination. Parent is an operator-controlled directory.
        if destination.exists():
            raise ValueError('Destination appeared during export')
        stage.rename(destination)
        return manifest
    finally:
        db.close()
        if stage.exists():
            shutil.rmtree(stage)


def verify(bundle):
    bundle = Path(bundle)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('format') != 'newton-hr-export/v1':
        raise ValueError('Unsupported export format')
    for table, meta in manifest['tables'].items():
        if not table.replace('_', '').isalnum():
            raise ValueError('Invalid table name')
        path = bundle / (table + '.jsonl')
        if path.is_symlink() or digest(path) != meta['sha256']:
            raise ValueError('Checksum mismatch: ' + table)
        count = 0
        keys = set()
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                if set(row) != set(meta['columns']):
                    raise ValueError('Columns mismatch: ' + table)
                key = tuple(row[k] for k in meta['primary_key'])
                if key in keys:
                    raise ValueError('Duplicate primary key: ' + table)
                keys.add(key)
                count += 1
        if count != meta['rows']:
            raise ValueError('Row count mismatch: ' + table)
    return {t: m['rows'] for t, m in manifest['tables'].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('export')
    p.add_argument('--source', required=True)
    p.add_argument('--destination', required=True)
    p = commands.add_parser('verify')
    p.add_argument('bundle')
    args = parser.parse_args()
    if args.command == 'export':
        result = export(args.source, args.destination)
        print(json.dumps({'tables': len(result['tables']), 'cutover_ready': False}))
    else:
        print(json.dumps(verify(args.bundle), sort_keys=True))


if __name__ == '__main__':
    main()
