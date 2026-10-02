# -*- coding: utf-8 -*-
"""请假 / 缺勤登记 —— 假别配置、配额折算、余额账本(附件10 落地)。

设计要点:
- 三类合同(full_time/temporal/autonomo)决定可见假别与配额算法。
- 自雇(autonomo)只见「不可用登记 INDISP」:register_only + 无配额 + 不带薪,防伪自雇。
- 余额账本:剩余 = quota - used - pending。提交冻结 pending,生效转 used,驳回/撤回释放。
逻辑放这里(纯函数、吃 session),便于单测;路由在 main.py 调用。
"""
import datetime as dt
from . import models

CONTRACTS = ["full_time", "temporal", "autonomo"]
CONTRACT_LABEL = {"full_time": "全职", "temporal": "临时", "autonomo": "自雇"}
STATUS_LABEL = {
    "draft": "草稿", "pending": "待审批", "approved": "已批准", "rejected": "已驳回",
    "cancelled": "已撤回", "effective": "已生效", "done": "已完成", "registered": "已登记",
}
_DEDUCT_RULES = ("fixed", "prorated")   # 会占用配额的规则

# HR 首次进入时自动预置(可再增删改);取自附件8 与集体协议
DEFAULT_TYPES = [
    dict(code="VAC", name_zh="年假", name_es="Vacaciones", applies_to="full_time,temporal",
         payable=True, nature="approvable", unit="day", advance_days=15, proof_required=False,
         quota_rule="prorated", quota_value=23, period_basis="calendar", sort=10,
         proof_hint=""),
    dict(code="ASUNTOS", name_zh="个人事务假", name_es="Asuntos propios", applies_to="full_time,temporal",
         payable=True, nature="approvable", unit="day", advance_days=3, proof_required=False,
         quota_rule="fixed", quota_value=1, period_basis="calendar", sort=20, proof_hint=""),
    dict(code="LEGAL", name_zh="普通/法定事假", name_es="Permiso retribuido", applies_to="full_time,temporal",
         payable=True, nature="register_only", unit="day", advance_days=3, proof_required=True,
         quota_rule="by_proof", quota_value=0, period_basis="calendar", sort=30,
         proof_hint="按事由上传对应材料(婚假/丧假/搬家等),法定假不可驳"),
    dict(code="BAJA", name_zh="病假", name_es="Baja médica", applies_to="full_time,temporal",
         payable=True, nature="register_only", unit="day", advance_days=0, proof_required=True,
         quota_rule="by_proof", quota_value=0, period_basis="calendar", sort=40,
         proof_hint="医疗停工证明 parte de baja(3 个工作日内上传)"),
    dict(code="OT", name_zh="调休", name_es="Compensación de horas", applies_to="full_time,temporal",
         payable=True, nature="approvable", unit="day", advance_days=0, proof_required=False,
         quota_rule="by_proof", quota_value=0, period_basis="calendar", sort=50,
         proof_hint="与已批准加班等量;自加班之日起 3 个月内休完"),
    dict(code="INDISP", name_zh="不可用登记", name_es="Comunicación de indisponibilidad",
         applies_to="autonomo", payable=False, nature="register_only", unit="day", advance_days=0,
         proof_required=False, quota_rule="none", quota_value=0, period_basis="calendar", sort=60,
         proof_hint="服务提供方排期通知,非请假,不带薪不配额"),
]


def seed_types(s):
    """空目录时预置默认假别。已存在则不动。"""
    if s.query(models.LeaveType).count() == 0:
        for d in DEFAULT_TYPES:
            s.add(models.LeaveType(**d))
        s.commit()


def contract_of(emp):
    return (getattr(emp, "contract_type", None) or "full_time")


def period_of(d, basis="calendar"):
    """原型:自然年。服务年度(service)可后续按入职周年切,这里仍返回年份占位。"""
    return str(d.year)


def working_days(a, b):
    """区间内工作日(周一~周五)计数,含首尾。周六日不计(与附件9 排班默认口径一致,粗算)。"""
    if not a or not b or b < a:
        return 0
    n, d = 0, a
    while d <= b:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n


def compute_quota(emp, lt, period):
    """年度额度。full_time=quota_value;temporal=按当年在职比例折算 23×在职天数/365;autonomo=0。
    by_proof/none 规则不设额(病假依证明、法定假、自雇不可用)。"""
    if lt.quota_rule not in _DEDUCT_RULES:
        return 0.0
    ct = contract_of(emp)
    if ct == "autonomo":
        return 0.0
    base = float(lt.quota_value or 0)
    if lt.quota_rule == "fixed":
        return base
    # prorated
    if ct == "temporal":
        year = int(period)
        ystart, yend = dt.date(year, 1, 1), dt.date(year, 12, 31)
        hire = emp.start_date or ystart
        leave = emp.end_date or yend
        a, b = max(hire, ystart), min(leave, yend)
        days = max(0, min((b - a).days + 1, 366))
        return round(base * days / 365.0, 1)
    return base   # full_time 的 prorated → 全额


def types_for(s, emp):
    """员工按合同类型可见的启用假别(已排序)。"""
    ct = contract_of(emp)
    out = []
    for lt in s.query(models.LeaveType).filter_by(active=True).order_by(models.LeaveType.sort).all():
        if ct in [x.strip() for x in (lt.applies_to or "").split(",") if x.strip()]:
            out.append(lt)
    return out


def ensure_entitlement(s, emp, lt, period):
    """取/建 员工×假别×年度 的余额行;未被 HR override 的额度跟随合同/入职自动重算。"""
    row = (s.query(models.LeaveEntitlement)
           .filter_by(employee_id=emp.id, leave_type_id=lt.id, period=period).first())
    if not row:
        row = models.LeaveEntitlement(employee_id=emp.id, leave_type_id=lt.id, period=period,
                                      quota=compute_quota(emp, lt, period), used=0, pending=0)
        s.add(row); s.flush()
    elif row.override_by is None:
        q = compute_quota(emp, lt, period)
        if abs((row.quota or 0) - q) > 1e-6:
            row.quota = q
    return row


def remaining(row):
    return round((row.quota or 0) - (row.used or 0) - (row.pending or 0), 1)


def _bal(s, emp_id, lt_id, period):
    return (s.query(models.LeaveEntitlement)
            .filter_by(employee_id=emp_id, leave_type_id=lt_id, period=period).first())


def deducts(lt):
    return lt.quota_rule in _DEDUCT_RULES


# ---------- 状态迁移 + 余额联动(纯逻辑,调用方负责 commit + 写 LeaveApproval 留痕) ----------
def on_submit(s, req, lt):
    """提交:可审批→冻结 pending 转 pending;仅登记→直接 effective(占额则转 used)。返回最终 status。"""
    if lt.nature == "register_only":
        req.status = "effective"
        if deducts(lt):
            b = _bal(s, req.employee_id, req.leave_type_id, req.period)
            if b:
                b.used = round((b.used or 0) + req.amount, 1)
    else:
        req.status = "pending"
        if deducts(lt):
            b = _bal(s, req.employee_id, req.leave_type_id, req.period)
            if b:
                b.pending = round((b.pending or 0) + req.amount, 1)
    return req.status


def on_approve(s, req, lt):
    if req.status != "pending":
        return
    req.status = "effective"
    if deducts(lt):
        b = _bal(s, req.employee_id, req.leave_type_id, req.period)
        if b:
            b.pending = max(0.0, round((b.pending or 0) - req.amount, 1))
            b.used = round((b.used or 0) + req.amount, 1)


def on_reject(s, req, lt):
    if req.status != "pending":
        return
    req.status = "rejected"
    if deducts(lt):
        b = _bal(s, req.employee_id, req.leave_type_id, req.period)
        if b:
            b.pending = max(0.0, round((b.pending or 0) - req.amount, 1))


def on_cancel(s, req, lt):
    """撤回:仅未生效(pending)可由本人撤;释放 pending。返回是否成功。"""
    if req.status != "pending":
        return False
    req.status = "cancelled"
    if deducts(lt):
        b = _bal(s, req.employee_id, req.leave_type_id, req.period)
        if b:
            b.pending = max(0.0, round((b.pending or 0) - req.amount, 1))
    return True
