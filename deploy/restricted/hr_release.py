#!/usr/bin/python3
"""Root-owned forced SSH command. Only HR code and the fixed HR service are mutable."""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import time

ROOT = Path('/var/lib/newton-hr-deploy')
POLICY = Path('/etc/newton-hr-deploy')
DOCKER = '/usr/bin/docker'
MAX_ARCHIVE = 16 * 1024 * 1024


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root'}).stdout


def extract_code(archive, destination):
    """Ignore all non-runtime files; reject unsafe members, secrets and links."""
    total = 0
    with tarfile.open(archive, 'r:') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe archive path')
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise ValueError('Archive links/special files are forbidden')
            if path.parts[0] not in {'hr', 'docs'} and member.name != 'requirements.txt':
                continue
            if any(p.startswith('.') for p in path.parts) or path.suffix in {'.pem','.key','.db'}:
                raise ValueError('Private files are forbidden in code releases')
            total += member.size
            if total > MAX_ARCHIVE:
                raise ValueError('Unpacked source too large')
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as src, target.open('xb') as dst:
                    dst.write(src.read())
                target.chmod(0o644)
    if not (destination/'hr/main.py').is_file():
        raise ValueError('Missing HR application')
    return destination


def compose(*args):
    return run(DOCKER,'compose','-p','hr','-f',str(POLICY/'compose.json'),*args)


def healthy():
    for _ in range(15):
        result = run(DOCKER,'inspect','--format','{{.State.Health.Status}}','hr-app',capture=True).strip()
        if result == 'healthy':
            return True
        time.sleep(2)
    return False


def main():
    os.umask(0o077)
    command = os.environ.get('SSH_ORIGINAL_COMMAND','').strip()
    if command == 'status':
        print(run(DOCKER,'inspect','--format','{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}','hr-app',capture=True))
        if (ROOT/'current.json').exists():
            print((ROOT/'current.json').read_text())
        return
    if command == 'logs':
        run(DOCKER,'logs','--tail','100','hr-app')
        return
    match = re.fullmatch(r'release ([0-9a-f]{40})', command)
    if not match:
        raise ValueError('Allowed commands: status, logs, release <40-character commit SHA>')
    if not (POLICY/'enabled').is_file():
        raise ValueError('HR deployment is not activated by platform operations yet')
    sha = match.group(1)
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT/'release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive = sys.stdin.buffer.read(MAX_ARCHIVE+1)
        if len(archive) > MAX_ARCHIVE:
            raise ValueError('Source archive exceeds 16 MiB')
        # SHA is a caller-supplied revision label; payload digest is the audit identity.
        stamp = str(time.time_ns())
        release = ROOT/'releases'/(sha+'-'+stamp)
        release.mkdir(parents=True)
        archive_path = release/'source.tar';archive_path.write_bytes(archive)
        context = release/'context';context.mkdir()
        extract_code(archive_path,context)
        if (context/'requirements.txt').read_bytes() != (POLICY/'requirements.txt').read_bytes():
            raise ValueError('Dependency changes require a reviewed platform runtime update')
        base = (POLICY/'runtime-image').read_text().strip()
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',base):
            raise ValueError('Invalid fixed runtime image')
        (context/'Dockerfile').write_text('FROM '+base+'\nUSER root\nRUN rm -rf /app/hr /app/docs\nCOPY --chown=10001:10001 hr /app/hr\nCOPY --chown=10001:10001 docs /app/docs\nUSER 10001\n')
        image = 'hr-release:'+sha
        run(DOCKER,'build','--network','none','--tag',image,str(context))
        # Back up the HR SQLite only; no stuff mount or key is accessible to this job.
        backup = ROOT/'backups'/stamp;backup.mkdir(parents=True)
        backup_code = "import sqlite3; s=sqlite3.connect('file:/data/hr.db?mode=ro',uri=True); d=sqlite3.connect('/backup/hr.db'); s.backup(d); assert d.execute('pragma integrity_check').fetchone()[0]=='ok'"
        run(DOCKER,'run','--rm','--network','none','--user','0','--entrypoint','python',
            '-v','hr_hr-data:/data:ro','-v',str(backup)+':/backup',base,'-c',backup_code)
        previous = run(DOCKER,'inspect','--format','{{.Image}}','hr-app',capture=True).strip()
        run(DOCKER,'tag',image,'hr-managed:active')
        try:
            compose('up','-d','--no-build','--no-deps','hr-app')
            if not healthy():
                raise RuntimeError('HR health check failed')
        except Exception:
            run(DOCKER,'tag',previous,'hr-managed:active')
            compose('up','-d','--no-build','--no-deps','hr-app')
            raise RuntimeError('HR image restored; database was not rolled back. Platform must inspect any data migration before retrying')
        record = {'revision_label':sha,'archive_sha256':hashlib.sha256(archive).hexdigest(),
                  'previous_image':previous,'image':image,'backup':str(backup),'at':int(time.time())}
        (ROOT/'current.json').write_text(json.dumps(record)+'\n')
        print(json.dumps(record))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('HR deployment stopped: '+str(exc),file=sys.stderr)
        sys.exit(1)
