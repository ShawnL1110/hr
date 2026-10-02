"""Read-only HR pilot: scoped personnel, leave, attendance and document access.

Only the imported HR database is read. This module never opens stuff's database.
"""
from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse

PROFILE_FIELDS = ('id','name','phone','email','birth_date','address','ssn','bank_holder',
                  'bank_id','bank_iban','bank_name','contract_type','status','start_date',
                  'end_date','reg_date','emp_category','puesto','tipo_contrato',
                  'grupo_profesional','centro_trabajo')


class Portal:
    def __init__(self, path, files):
        self.path = Path(path).absolute()
        self.files = Path(files).absolute()

    @contextmanager
    def read(self):
        if not self.path.is_file():
            raise HTTPException(503, 'HR 数据尚未导入')
        connection = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            version = connection.execute('SELECT version FROM hr_schema_version').fetchone()
            if not version or version[0] != 1:
                raise HTTPException(503, 'HR 数据版本不兼容')
            yield connection
        except sqlite3.DatabaseError:
            raise HTTPException(503, 'HR 数据暂时不可用')
        finally:
            connection.close()

    @staticmethod
    def scoped(identity, employee_id, permission):
        own = identity.get('employee_id')
        eid = employee_id if employee_id is not None else own
        if not isinstance(eid, int) or isinstance(eid, bool) or eid <= 0:
            raise HTTPException(403, '账号尚未绑定员工')
        if eid != own and permission not in identity.get('permissions', []):
            raise HTTPException(403, '无权查看其他员工资料')
        return eid

    def attachment(self, source_path):
        """Map a legacy path to an explicitly copied, content-verified private file."""
        try:
            mapping = json.loads((self.files/'manifest.json').read_text())
            entry = mapping['files'][source_path]
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid file path')
            root = self.files.resolve()
            target = (root/relative).resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError('File escapes root')
            checksum = hashlib.sha256()
            with target.open('rb') as f:
                for block in iter(lambda: f.read(1024*1024), b''):
                    checksum.update(block)
            if checksum.hexdigest() != entry['sha256']:
                raise ValueError('File checksum mismatch')
            return target
        except (OSError, KeyError, ValueError, TypeError):
            raise HTTPException(404, '附件尚未迁移或校验未通过')


def register(app, current, settings):
    data = Path(settings.get('HR_DATA_DIR', './data'))
    portal = Portal(settings.get('HR_DATABASE', str(data/'hr.db')),
                    settings.get('HR_FILES_DIR', str(data/'files')))

    @app.get('/api/employees')
    async def employees(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        identity, _ = await current(request)
        if not set(identity['permissions']) & {'profile.read_all','leave.read_all','documents.read_all'}:
            raise HTTPException(403, '需要 HR 查阅权限')
        with portal.read() as c:
            total = c.execute('SELECT count(*) FROM employee').fetchone()[0]
            rows = c.execute('SELECT id,name,status,puesto FROM employee ORDER BY id LIMIT ? OFFSET ?', (limit,offset))
            return {'items': [dict(r) for r in rows], 'total':total, 'offset':offset, 'limit':limit}

    @app.get('/api/profile')
    async def profile(request: Request, employee_id: int | None = None):
        identity, _ = await current(request)
        eid = portal.scoped(identity, employee_id, 'profile.read_all')
        with portal.read() as c:
            row = c.execute('SELECT '+','.join(PROFILE_FIELDS)+' FROM employee WHERE id=?',(eid,)).fetchone()
            if not row:
                raise HTTPException(404, '员工档案不存在')
            return dict(row)

    @app.get('/api/leave')
    async def leave(request: Request, employee_id: int | None = None,
                    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        identity, _ = await current(request)
        eid = portal.scoped(identity, employee_id, 'leave.read_all')
        with portal.read() as c:
            rows = c.execute('''SELECT r.id,r.leave_type_id,t.name_zh,t.name_es,t.unit,r.date_from,r.date_to,
                r.amount,r.reason,r.status,r.proof_pending,r.decide_reason,r.created_at,
                CASE WHEN r.proof_path IS NOT NULL AND r.proof_path<>'' THEN 1 ELSE 0 END AS has_proof
                FROM leave_request r LEFT JOIN leave_type t ON t.id=r.leave_type_id
                WHERE r.employee_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?''',(eid,limit,offset))
            items = [dict(r) for r in rows]
            total = c.execute('SELECT count(*) FROM leave_request WHERE employee_id=?',(eid,)).fetchone()[0]
            balances = [dict(r) for r in c.execute('''SELECT e.period,t.name_zh,t.name_es,t.unit,e.quota,e.used,e.pending,
                COALESCE(e.quota,0)-COALESCE(e.used,0)-COALESCE(e.pending,0) AS remaining
                FROM leave_entitlement e JOIN leave_type t ON t.id=e.leave_type_id
                WHERE e.employee_id=? ORDER BY e.period DESC,t.sort,t.id''',(eid,))]
            return {'items':items, 'balances':balances,'total':total, 'offset':offset,'limit':limit}

    @app.get('/api/attendance')
    async def attendance(request: Request, date_from: date, date_to: date, employee_id: int | None = None):
        identity, _ = await current(request)
        eid = portal.scoped(identity, employee_id, 'leave.read_all')
        if date_to < date_from or date_to-date_from > timedelta(days=366):
            raise HTTPException(400, '日期范围须为 0 至 366 天')
        args = (eid,date_from.isoformat(),date_to.isoformat())
        with portal.read() as c:
            logs = [dict(r) for r in c.execute('''SELECT day,first_at,last_at FROM attendance_log
                WHERE employee_id=? AND day>=? AND day<=? ORDER BY day DESC''',args)]
            entries = [dict(r) for r in c.execute('''SELECT date,present,wa_ok,daily_target_met,violation,qc_deduction,note
                FROM daily_work_entry WHERE employee_id=? AND date>=? AND date<=? ORDER BY date DESC''',args)]
            return {'activity': logs, 'work_entries': entries,
                    'note':'上线与活跃记录来自 stuff，不等同于出勤审批或计薪工时。'}

    @app.get('/api/documents')
    async def documents(request: Request, employee_id: int | None = None,
                        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        identity, _ = await current(request)
        eid = portal.scoped(identity, employee_id, 'documents.read_all')
        with portal.read() as c:
            rows = c.execute('''SELECT a.id,a.reg_id,a.mode,a.status,a.sent_at,a.first_open_at,a.confirmed_at,a.signed_at,
                f.name AS document_name,f.version,
                CASE WHEN COALESCE(NULLIF(a.pdf_path,''),NULLIF(f.pdf_path,'')) IS NOT NULL THEN 1 ELSE 0 END AS has_original,
                CASE WHEN NULLIF(a.signed_pdf_path,'') IS NOT NULL THEN 1 ELSE 0 END AS has_signed,
                CASE WHEN NULLIF(a.receipt_path,'') IS NOT NULL THEN 1 ELSE 0 END AS has_receipt,
                CASE WHEN NULLIF(a.final_pdf_path,'') IS NOT NULL THEN 1 ELSE 0 END AS has_final,
                CASE WHEN NULLIF(a.manual_upload_path,'') IS NOT NULL THEN 1 ELSE 0 END AS has_manual
                FROM empdoc_assignment a JOIN empdoc_file f ON f.id=a.file_id
                WHERE a.employee_id=? ORDER BY a.sent_at DESC,a.id DESC LIMIT ? OFFSET ?''',(eid,limit,offset))
            items = [dict(r) for r in rows]
            total = c.execute('SELECT count(*) FROM empdoc_assignment WHERE employee_id=?',(eid,)).fetchone()[0]
            return {'items': items,'total':total,'offset':offset,'limit':limit}

    @app.get('/api/documents/{assignment_id}/download')
    async def download(request: Request, assignment_id: int, kind: str = 'original'):
        identity, _ = await current(request)
        columns = {'original':'pdf_path','signed':'signed_pdf_path','receipt':'receipt_path',
                   'final':'final_pdf_path','manual':'manual_upload_path'}
        if kind not in columns:
            raise HTTPException(400, '文件类型无效')
        with portal.read() as c:
            row = c.execute('SELECT * FROM empdoc_assignment WHERE id=?',(assignment_id,)).fetchone()
            if not row:
                raise HTTPException(404, '文件不存在')
            portal.scoped(identity, row['employee_id'], 'documents.read_all')
            path = row[columns[kind]]
            if kind == 'original' and not path:
                shared = c.execute('SELECT pdf_path FROM empdoc_file WHERE id=?',(row['file_id'],)).fetchone()
                path = shared[0] if shared else None
            if not path:
                raise HTTPException(404, '该版本文件不存在')
            target = portal.attachment(path)
        return FileResponse(target, filename=f'document-{assignment_id}-{kind}{target.suffix}',
                            media_type='application/octet-stream', content_disposition_type='attachment')

    @app.get('/api/leave/{request_id}/proof')
    async def proof(request: Request, request_id: int):
        identity, _ = await current(request)
        with portal.read() as c:
            row = c.execute('SELECT employee_id,proof_path FROM leave_request WHERE id=?',(request_id,)).fetchone()
            if not row or not row['proof_path']:
                raise HTTPException(404, '证明不存在')
            portal.scoped(identity, row['employee_id'], 'leave.read_all')
            target = portal.attachment(row['proof_path'])
        return FileResponse(target, filename=f'leave-{request_id}{target.suffix}',
                            media_type='application/octet-stream', content_disposition_type='attachment')
