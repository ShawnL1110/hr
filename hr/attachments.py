"""Copy only HR-referenced attachments from mapped backup roots; never entire volumes."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from .migration import verify, digest, canonical

FIELDS = {
    'employee': ('ss_scan_path','id_scan_path'),
    'candidate': ('resume_path',),
    'leave_request': ('proof_path',),
    'empdoc_file': ('pdf_path',),
    'empdoc_assignment': ('pdf_path','receipt_path','signed_pdf_path','final_pdf_path','manual_upload_path'),
}


def references(bundle):
    verify(bundle)
    found = {}
    def add(path, expected=None):
        if not path:
            return
        if not isinstance(path,str) or '\x00' in path or '..' in PurePosixPath(path).parts:
            raise ValueError('Invalid attachment reference')
        found.setdefault(path,set())
        if expected:
            found[path].add(expected)
    for table, fields in FIELDS.items():
        with (Path(bundle)/(table+'.jsonl')).open() as f:
            for line in f:
                row=json.loads(line)
                for field in fields:
                    add(row.get(field),row.get('sha256') if field=='pdf_path' else None)
    with (Path(bundle)/'empdoc_setting.jsonl').open() as f:
        for line in f:
            row=json.loads(line)
            if row['skey']=='firma_empresa_path':
                add(row['sval'])
    return found


def source_file(legacy, roots):
    legacy=PurePosixPath(legacy)
    # Longest matching prefix wins, explicitly supplied by operator.
    for prefix, local in sorted(roots,key=lambda r:len(PurePosixPath(r[0]).parts),reverse=True):
        prefix=PurePosixPath(prefix)
        if legacy.is_relative_to(prefix):
            root=Path(local).resolve(strict=True)
            target=(root/str(legacy.relative_to(prefix))).resolve(strict=True)
            if target.is_relative_to(root) and target.is_file():
                return target
            raise ValueError('Attachment escapes mapped backup root')
    raise ValueError('Attachment has no mapped backup root')


def copy_bundle(bundle, destination, roots):
    refs=references(bundle)
    destination=Path(destination).absolute()
    if destination.exists():
        raise ValueError('Refusing to overwrite attachment directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.hr-files-',dir=destination.parent))
    stage.chmod(0o700)
    manifest={'format':'newton-hr-files/v1','files':{}}
    try:
        for legacy,expected in sorted(refs.items()):
            source=source_file(legacy,roots)
            checksum=digest(source)
            if expected and expected!={checksum}:
                raise ValueError('Original document hash mismatch')
            suffix=source.suffix.lower()
            if suffix not in {'.pdf','.png','.jpg','.jpeg','.webp','.doc','.docx'}:
                suffix='.bin'
            filename=checksum+suffix
            target=stage/filename
            if not target.exists():
                shutil.copyfile(source,target)
                target.chmod(0o600)
            if digest(target)!=checksum:
                raise ValueError('Attachment changed during copy')
            manifest['files'][legacy]={'path':filename,'sha256':checksum}
        (stage/'manifest.json').write_bytes(canonical(manifest)+b'\n')
        (stage/'manifest.json').chmod(0o600)
        if destination.exists():
            raise ValueError('Destination appeared during copy')
        stage.rename(destination)
        return {'references':len(refs),'files':len({v['path'] for v in manifest['files'].values()})}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--root',action='append',required=True,help='Original root=local backup root; repeat for each volume')
    args=parser.parse_args()
    roots=[]
    for value in args.root:
        parts=value.split('=',1)
        if len(parts)!=2 or not all(parts):
            parser.error('Expected --root original=local')
        roots.append(parts)
    print(json.dumps(copy_bundle(args.bundle,args.destination,roots)))


if __name__=='__main__':
    main()
