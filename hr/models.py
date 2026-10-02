"""HR-owned models extracted from stuff; business identities/facts are projections.

Initial schema v1. New production schema changes require reviewed migrations.
"""
import datetime
from sqlalchemy import (Column, Integer, String, Float, Date, DateTime, Text,
                        Boolean, ForeignKey, UniqueConstraint, Index)
from sqlalchemy.orm import declarative_base
Base = declarative_base()


def _now():
    return datetime.datetime.now()


class User(Base):
    """Identity projection; no passwords, sessions or authoritative permissions."""
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False)
    employee_id = Column(Integer, ForeignKey('employee.id'))
    status = Column(String(16))


class Employee(Base):
    """催收员工(与登录账号 User 分离:一个员工可无登录账号,也可有)。"""
    __tablename__ = "employee"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    team_id = Column(Integer, ForeignKey("team.id"))
    track = Column(String(16), default="collection")      # 体系:collection/legal/hr
    plan_id = Column(Integer, ForeignKey("salary_plan.id"))  # 绑定的薪酬策略;空=用本体系默认策略
    salary_plan = Column(String(16), default="current")   # 【弃用】旧字段,保留只为兼容历史数据
    emp_type = Column(String(16), default="internal")     # internal/external 内部/外部
    phone = Column(String(32))    # 员工手机号(西班牙,E.164 或裸9位);「员工文件」模块只读消费,HR 在组织架构维护
    phone_changed_at = Column(DateTime)   # v4.9 8.4:改号时间(新号 24h 内不可用于 C 签署)
    # 用工合同类型(请假模块用):full_time 全职 / temporal 临时 / autonomo 自雇。
    # 全职=完整法定假;临时=同权利但年假按在职比例折算;自雇=非雇员,只做「不可用登记」(不带薪不配额不审批)。
    contract_type = Column(String(16), default="full_time")
    status = Column(String(16), default="active")   # active/inactive
    start_date = Column(Date) # 入职日期(第一个工作日);设了则入职前的天数不计工资
    end_date = Column(Date)   # 离职日期(最后工作日);设了则离职当周仍计工资,只算到该日
    daily_hours = Column(Float)   # 每人自定义日工时(如法务6h);空=按岗位默认(组长8/组员按案件档)
    work_days = Column(Integer)   # 每周工作天数:5=周一~周五(周六也休),空/6=周一~周六(催收默认)
    sat_ot_hours = Column(Float)  # 周六加班工时:>0 则周六出勤额外按该工时×时薪计(如 Luis=8);空/0=不加班
    # 特殊工资模式(salary_plan=='special'):固定周底薪 + 日补贴(替代岗位津贴等),仍保留绩效/质检/违规
    base_weekly = Column(Float)      # 固定周底薪(不随出勤浮动),如 Luis 402
    allowance_daily = Column(Float)  # 每出勤日补贴,如 Luis 4.43
    # 付款银行账户(员工自助填写,工资导出自动带出)
    bank_holder = Column(String(128))   # 户名(收款人)
    bank_id = Column(String(64))        # 证件号 DNI/NIE
    bank_iban = Column(String(64))      # IBAN / 账号
    bank_name = Column(String(128))     # 开户行
    # 员工基本信息自助维护(NEWTON 需求·2026-09-23):员工端 /bank 自填,HR 端 /org 填 reg_date/emp_category
    birth_date = Column(Date)           # 出生日期(员工自填)
    email = Column(String(128))         # 联系邮箱(员工自填;与登录账号邮箱分开)
    ssn = Column(String(48))            # 西班牙社保号 Número de la Seguridad Social(员工自填)
    address = Column(Text)              # 完整居住地址 Domicilio(员工自填)
    ss_scan_path = Column(String(512))  # 社保证件扫描件路径(员工上传)
    id_scan_path = Column(String(512))  # NIE/DNI 证件扫描件路径(员工上传)
    reg_date = Column(Date)             # 转正日期(HR 填)
    emp_category = Column(String(24))   # 员工类别(HR 填,见 constants.EMP_CATEGORIES):contrato_prueba/contrato_fijo/parcial/autonomo/externo/externo_yingka/otro
    # 员工文件 v3.6 7.4-bis:远程办公协议附件一所需字段(HR 录入,进合同不可员工自助改)
    clausula_desplazamiento = Column(String(32))   # 通勤条款取值
    anexo1_ordenador = Column(String(32))          # 电脑由谁提供
    anexo1_movil = Column(String(32))              # 手机由谁提供
    anexo1_linea = Column(String(32))              # 电话线路由谁提供
    anexo1_comp_equipo_propio = Column(String(32)) # 是否适用自有设备补偿
    anexo1_reembolso_telefonia = Column(String(32))# 是否适用电话费报销
    anexo1_observaciones = Column(Text)            # 备注(无内容填 Ninguna.)
    # 员工文件 2026-09-28 #4.5:劳动协议标准字段(HR 录入,进合同正文)。与 contract_type(请假模块)独立。
    puesto = Column(String(128))              # 岗位 Puesto
    tipo_contrato = Column(String(64))        # 劳动合同类型 Tipo de contrato(Indefinido/Temporal…)
    grupo_profesional = Column(String(64))    # 职业组别 Grupo profesional(集体协议)
    centro_trabajo = Column(String(128))      # 工作地点 Centro de trabajo
    created_at = Column(DateTime, default=_now)



class Team(Base):
    __tablename__ = "team"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    leader_employee_id = Column(Integer, ForeignKey("employee.id"))
    institution = Column(String(64))   # 机构(手工归属):一个机构下有多个组;业绩地图机构对比按账户当日持有员工的组→机构聚合
    created_at = Column(DateTime, default=_now)



class DailyWorkEntry(Base):
    """组长按日录入的考勤/质检/WA/违规(工资浮动与扣款依据)。绩效达成率系统自动算,不在此。"""
    __tablename__ = "daily_work_entry"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    employee_id = Column(Integer, ForeignKey("employee.id"), nullable=False)
    present = Column(Integer, default=1)            # 出勤 1/0(现按违规自动推,保留列)
    qc_deduction = Column(Float, default=0.0)       # 当日质检扣款(由 qc_items 求和封顶5)
    qc_items = Column(String(256))                  # 选中的质检项 code,逗号分隔
    wa_ok = Column(Integer, default=0)              # WA达标 1/0 -> WA补贴
    daily_target_met = Column(Integer, default=0)   # (已改系统自动,不再手填)
    violation = Column(String(16), default="")      # 违规枚举(见 constants.VIOLATIONS)
    note = Column(String(512))
    submitted_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("date", "employee_id", name="uq_workentry"),
                      Index("ix_work_date", "date"))



class LeaderAttend(Base):
    """组长的手动出勤天数(周)。组长(尤其纯督导、不持账户)无排班信号默认满勤,允许管理员按周手动设定。
    仅上限/设定用:把该周计薪的出勤天数封到该值(≤自动算出的天数)。"""
    __tablename__ = "leader_attend"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, index=True)
    week_start = Column(Date)
    days = Column(Integer)              # 手动设定的出勤天数
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("employee_id", "week_start", name="uq_leader_attend"),)



class PayAdjustment(Base):
    """周/一次性调整项(月度催收之星、内推激励、临时激励等),按周计入。"""
    __tablename__ = "pay_adjustment"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False)
    employee_id = Column(Integer, ForeignKey("employee.id"), nullable=False)
    kind = Column(String(24))       # star/referral/incentive/other
    amount = Column(Float, default=0.0)   # 正=加,负=扣
    note = Column(String(256))
    created_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now)
    __table_args__ = (Index("ix_adj_week", "week_start", "employee_id"),)



class PkBonus(Base):
    """每日 PK 奖(手动):HR/组长按天给个别员工发的比赛奖金,系统不自动计算,直接加进当天绩效。
    每人每天一条(可覆盖);金额为正加、负扣。"""
    __tablename__ = "pk_bonus"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    employee_id = Column(Integer, ForeignKey("employee.id"), nullable=False)
    amount = Column(Float, default=0.0)
    note = Column(String(256))
    created_by = Column(Integer, ForeignKey("user.id"))
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("date", "employee_id", name="uq_pkbonus"),
                      Index("ix_pk_date", "date"))



class SalaryPlan(Base):
    """薪酬策略:某体系下的一个【具名薪酬包】(付薪方式/时薪/绩效档表/补贴)。
    员工绑定策略(不绑=用该体系默认策略);同一体系可并存多个策略 → 不同员工走不同策略,
    便于同期做 A/B 再对比。策略内部再按生效日期分版本(SalaryPlanVersion)。"""
    __tablename__ = "salary_plan"
    id = Column(Integer, primary_key=True)
    track = Column(String(16), default="collection")   # collection/legal/hr
    name = Column(String(64), nullable=False)
    is_default = Column(Boolean, default=False)   # 该体系默认策略(每体系应恰有一个)
    active = Column(Boolean, default=True)
    note = Column(String(256))
    created_at = Column(DateTime, default=_now)
    __table_args__ = (Index("ix_plan_track", "track"),)



class SalaryPlanVersion(Base):
    """某【体系】的工资+绩效方案版本(名称 + 生效日期)。算某天工资时,按该员工体系
    取「生效日≤该天」里最新的一版 → 改方案=新增一版,历史自动沿用旧版不受影响。
    - collection(催收):时薪/组长时薪/工时/岗位津贴/WA/全勤/交通 + 绩效档表(perf_bands)
    - legal(法务):时薪/工时 + 每结清一单奖金(settle_bonus)
    - hr(HR):时薪/工时(绩效暂无,预留)"""
    __tablename__ = "salary_plan_version"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("salary_plan.id"), index=True)  # 所属策略(权威)
    track = Column(String(16), default="collection")   # 冗余留存:迁移与兜底用
    effective_date = Column(Date, nullable=False)
    label = Column(String(64))
    # 付薪方式:hourly=时薪×工时×出勤天;fixed_base=固定周底薪(不随出勤)+日补贴×出勤天
    pay_mode = Column(String(16), default="hourly")
    base_weekly = Column(Float, default=0)         # 【fixed_base】固定周底薪
    allowance_daily = Column(Float, default=0)     # 【fixed_base】每出勤日补贴(替代岗位津贴等)
    hourly = Column(Float, default=9)          # 组员时薪
    leader_hourly = Column(Float, default=10)  # 组长时薪
    hours = Column(Float, default=8)
    position_daily = Column(Float, default=5)     # 岗位津贴/天
    wa_monthly = Column(Float, default=40)         # WA补贴/月(折日=÷标准工作日)
    full_attend_daily = Column(Float, default=0)   # 全勤奖/天
    transport_daily = Column(Float, default=0)     # 交通补贴/天
    settle_bonus = Column(Float, default=0)        # 【法务】每结清一单奖金€
    perf_bands = Column(Text)                      # 【催收】绩效档表 JSON(见 constants.bands_*)
    __table_args__ = (Index("ix_planver_date", "track", "effective_date"),)



class WorkHoursTier(Base):
    """工时档:D段(D-2/D-1/D0)按当日案件单数决定工时。S段用方案固定工时(plan.hours)。
    命中第一个 案件数 ≤ max_cases 的档。"""
    __tablename__ = "work_hours_tier"
    id = Column(Integer, primary_key=True)
    max_cases = Column(Integer, nullable=False)   # 案件数 ≤ 此值
    hours = Column(Float, nullable=False)          # 该档工时



class StagePerCase(Base):
    """S段每单激励:某(阶段×内外部)每回收一单奖励多少欧(如 S1 内部=3€/单)。
    D-1/D0 用 bono×系数,不走这里。缺配置即 0。"""
    __tablename__ = "stage_per_case"
    id = Column(Integer, primary_key=True)
    stage = Column(String(8), nullable=False)
    emp_type = Column(String(16), nullable=False)   # internal/external
    rate = Column(Float, default=0.0)               # 欧/单
    __table_args__ = (UniqueConstraint("stage", "emp_type", name="uq_percase"),)



class StagePerCaseVersion(Base):
    """S段每单激励【按生效日期的费率版本】。算某天工资时,取该(阶段×内外部)里
    「生效日 ≤ 该天」最新一版的费率;没有版本则回退 StagePerCase 基础值(视为最早基线)。
    改费率=新增一版并设生效日期,历史周按旧值算不受影响。"""
    __tablename__ = "stage_per_case_version"
    id = Column(Integer, primary_key=True)
    stage = Column(String(8), nullable=False)
    emp_type = Column(String(16), nullable=False)   # internal/external
    rate = Column(Float, default=0.0)               # 欧/单
    effective_date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("stage", "emp_type", "effective_date", name="uq_percase_ver"),
                      Index("ix_percase_ver", "stage", "emp_type", "effective_date"))



class WeeklyPayslip(Base):
    """周工资单快照。确认(confirmed)时冻结当周,考勤/绩效不再变。"""
    __tablename__ = "weekly_payslip"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False)
    employee_id = Column(Integer, ForeignKey("employee.id"), nullable=False)
    status = Column(String(16), default="draft")   # draft/confirmed
    net_pay = Column(Float, default=0.0)
    breakdown = Column(Text)     # 冻结时的明细 JSON
    confirmed_by = Column(Integer, ForeignKey("user.id"))
    confirmed_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("week_start", "employee_id", name="uq_payslip"),)



class Candidate(Base):
    """招聘候选人(HR 模块)。HR 上传简历/写面试时间;管理员确认面试、写面试/试用期意见。"""
    __tablename__ = "candidate"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)   # 候选人姓名
    position = Column(String(128))               # 应聘岗位
    phone = Column(String(64))                   # 联系方式
    resume_path = Column(String(256))            # 简历文件
    interview_time = Column(DateTime)            # 面试时间(HR 填)
    interview_link = Column(String(512))         # 面试链接
    interview_confirmed = Column(String(16))     # 面试确认:NULL/pending/confirmed(管理员)
    interview_opinion = Column(Text)             # 面试意见(管理员)
    onboard_date = Column(Date)                  # 入职时间
    probation_end = Column(Date)                 # 试用期至
    probation_opinion = Column(Text)             # 试用期意见(管理员)
    status = Column(String(16), default="待邀约")  # 见 constants.RECRUIT_STATUSES
    parse_status = Column(String(12))            # 批量导入简历解析:pending/done/error;None=手工录入
    declined = Column(Boolean, default=False)    # 候选人明确拒绝(不再重复联系;批量短信/连拨默认跳过)
    note = Column(Text)
    created_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class AttendanceLog(Base):
    """员工在线考勤:每员工每天一行。前台心跳(任意已登录工作页,约每 3 分钟)自动上报,
    记当天首次上线 first_at 与最后活跃 last_at → 自动打卡,不依赖员工手动。时区=西班牙。"""
    __tablename__ = "attendance_log"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, index=True)
    day = Column(String(10), index=True)   # YYYY-MM-DD(西班牙当地)
    first_at = Column(DateTime)
    last_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("employee_id", "day", name="uq_att_emp_day"),)



class LeaveType(Base):
    """假别目录(HR 后台维护)。员工端按合同类型过滤 applies_to 后只读消费。"""
    __tablename__ = "leave_type"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)   # 系统代码,如 VAC/ASUNTOS/BAJA/LEGAL/OT/INDISP
    name_zh = Column(String(64), nullable=False)
    name_es = Column(String(96))
    applies_to = Column(String(48), default="full_time,temporal")  # 逗号分隔:full_time/temporal/autonomo
    payable = Column(Boolean, default=True)                  # 是否带薪
    nature = Column(String(16), default="approvable")        # approvable 可审批 / register_only 仅登记(法定假/病假/自雇)
    unit = Column(String(8), default="day")                  # day 工作日 / hour 小时
    advance_days = Column(Integer, default=0)                # 提前期(自然日);0=当日通报
    proof_required = Column(Boolean, default=False)          # 是否需上传证明
    proof_hint = Column(String(128))                         # 材料提示,如「医疗停工证明 parte de baja」
    quota_rule = Column(String(16), default="none")          # fixed 固定天数 / prorated 按在职比例 / by_proof 依证明不设额 / none 无额
    quota_value = Column(Float, default=0)                   # 年度基准额(fixed/prorated 用),单位同 unit
    period_basis = Column(String(16), default="calendar")   # calendar 自然年 / service 服务年度
    carryover = Column(Boolean, default=False)               # 未休是否结转下期
    sort = Column(Integer, default=100)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)



class LeaveEntitlement(Base):
    """员工 × 假别 × 年度 的配额与余额账本。剩余 = quota - used - pending。"""
    __tablename__ = "leave_entitlement"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employee.id"), index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_type.id"), index=True)
    period = Column(String(8), nullable=False)               # 年度标识,如 '2026'
    quota = Column(Float, default=0)                         # 额度(系统计算,HR 可 override)
    used = Column(Float, default=0)                          # 已生效占用
    pending = Column(Float, default=0)                       # 待审批冻结
    override_by = Column(Integer, ForeignKey("user.id"))     # HR 手动改额留痕
    override_note = Column(String(200))
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("employee_id", "leave_type_id", "period", name="uq_entitlement"),)



class LeaveRequest(Base):
    """请假 / 不可用 申请单。状态机(附件8):draft→pending→(approved|rejected|cancelled)→effective→done;
    仅登记类(register_only)由 pending 直接到 effective。"""
    __tablename__ = "leave_request"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employee.id"), index=True)
    contract_type = Column(String(16))                       # 提交时快照(full_time/temporal/autonomo)
    leave_type_id = Column(Integer, ForeignKey("leave_type.id"), index=True)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    amount = Column(Float, default=0)                        # 天数或小时数(按假别 unit)
    reason = Column(Text)                                    # 事由;法定假在此备注具体是什么(婚假/丧假/搬家等)
    proof_path = Column(String(256))                         # 证明文件
    proof_pending = Column(Boolean, default=False)           # 待补证明
    advance_ok = Column(Boolean, default=True)               # 是否满足提前期(否则标「未达提前期」仍可提交)
    status = Column(String(16), default="pending", index=True)
    period = Column(String(8))                               # 归属年度(扣哪年配额)
    decided_by = Column(Integer, ForeignKey("user.id"))
    decided_at = Column(DateTime)
    decide_reason = Column(String(300))                      # 驳回理由(附件8:年假驳回理由必填并存档)
    created_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now, index=True)



class LeaveApproval(Base):
    """审批 / 登记留痕(append-only,保存四年)。每次操作一行。"""
    __tablename__ = "leave_approval"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("leave_request.id"), index=True)
    actor_id = Column(Integer, ForeignKey("user.id"))
    actor_role = Column(String(16))                          # 操作人角色快照
    action = Column(String(16))                              # submit/approve/reject/cancel/register/proof
    reason = Column(String(300))
    created_at = Column(DateTime, default=_now)



class EmpDocType(Base):
    """文件类型配置表(设置页可增删,不用改代码)。最低方式=系统唯一强制的规则。"""
    __tablename__ = "empdoc_type"
    id = Column(Integer, primary_key=True)
    name_es = Column(String(120), nullable=False)            # 西语类型名(如 Contrato de trabajo)
    name_zh = Column(String(120))                            # 中文仅管理端参考
    default_mode = Column(String(1), default="A")           # A/B/C 推送时默认带出,可改
    min_mode = Column(String(1), default="A")               # 不能选比它更低的方式(A<B<C)
    max_mode = Column(String(1))                            # 不能选比它更高的方式(v3.6 3.1);空=C(不封顶)
    default_text_key = Column(String(48))                    # 默认勾选文字(empdoc_text.usage_key)
    use_template = Column(Boolean, default=False)           # v3.6 §3.1:是=用系统模板按人渲染;否=上传现成PDF。用模板者恒个人专属
    needs_efectos = Column(Boolean, default=False)          # v4.9 3.1/item7:推送时必填生效日期且不早于推送日
    personal = Column(Boolean, default=False)               # 是=每人各传一份;否=同一份推多人
    external_warn = Column(Boolean, default=False)           # 推给「外部合作人员」时弹 falso autónomo 提醒
    sort = Column(Integer, default=100)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)



class EmpDocText(Base):
    """文字模板库 + 回执/签署页/声明正文模板(设置页维护)。只存西语,{{变量}} 占位。"""
    __tablename__ = "empdoc_text"
    id = Column(Integer, primary_key=True)
    usage_key = Column(String(48), unique=True, index=True)  # checkbox_* / receipt_b / sign_page_c / declar_manual_first ...
    kind = Column(String(16), default="checkbox")            # checkbox 勾选文字 / receipt 回执 / signpage 签署页 / declaration 声明正文
    label_zh = Column(String(120))                           # 用途(管理端看)
    text_es = Column(Text)                                   # 西语正文(系统显示/生成用)
    sort = Column(Integer, default=100)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class EmpDocPackage(Base):
    """一次推送=一个文件包(1+ 份文件)。含 C 类时全包一次验证码。"""
    __tablename__ = "empdoc_package"
    id = Column(Integer, primary_key=True)
    code = Column(String(24), unique=True, index=True)       # 文件包编号(展示/回执引用)
    pusher_user_id = Column(Integer, ForeignKey("user.id"), index=True)
    declaration = Column(Text)                               # 声明正文(可选,长文本)
    check_text = Column(Text)                                # 勾选文字快照(推送时定稿·全部一次勾选时的汇总文字)
    audience_json = Column(Text)                             # 对象筛选条件快照(留痕)
    status = Column(String(12), default="published")         # published / draft
    is_test = Column(Boolean, default=False)                # v3.6 第十二部分:测试数据(可批量删除·PDF加水印·不进导出)
    created_at = Column(DateTime, default=_now, index=True)



class EmpDocFile(Base):
    """包内每份文件。个人专属文件的逐人 PDF 落在 assignment.pdf_path;非专属放这里 pdf_path。"""
    __tablename__ = "empdoc_file"
    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, ForeignKey("empdoc_package.id"), index=True)
    doc_type_id = Column(Integer, ForeignKey("empdoc_type.id"))
    mode = Column(String(1), default="A")                   # A/B/C(定稿,≥类型最低方式)
    name = Column(String(200))                              # documento_nombre(文件名称)
    version = Column(String(32))                            # documento_version
    filename = Column(String(200))                          # documento_archivo(PDF 原文件名)
    fecha_efectos = Column(String(10))                      # v4.9 item7:生效日期(yyyy-mm-dd),需要的类型推送时填
    template_id = Column(Integer)                           # v3.6 7.3:用系统模板渲染时记当时模板版本(已推送不随模板改动重渲染)
    check_text = Column(Text)                               # v3.6 3.3:该文件自己的勾选文字(按类型绑定,含{{变量}}未渲染)
    pdf_path = Column(String(300))                          # 非个人专属:共用 PDF 路径
    sha256 = Column(String(64))                             # 非个人专属:文件哈希
    personal = Column(Boolean, default=False)
    sort = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)



class EmpDocAssignment(Base):
    """每份文件 × 每个员工 一条留痕(append 后仅状态/时间戳推进,不可回改内容)。"""
    __tablename__ = "empdoc_assignment"
    id = Column(Integer, primary_key=True)
    reg_id = Column(String(24), unique=True, index=True)     # id_registro(回执引用)
    package_id = Column(Integer, ForeignKey("empdoc_package.id"), index=True)
    file_id = Column(Integer, ForeignKey("empdoc_file.id"), index=True)
    employee_id = Column(Integer, ForeignKey("employee.id"), index=True)
    mode = Column(String(1), default="A")
    status = Column(String(24), default="sent")             # sent/read/confirmed/signed/entregado_sin_confirmar
    pdf_path = Column(String(300))                          # 个人专属:该员工那份 PDF
    sha256 = Column(String(64))                             # 个人专属:该员工文件哈希
    text_confirmed = Column(Text)                           # 员工勾选原文快照
    phone_snapshot = Column(String(32))                     # 确认/签署时刻档案手机号快照
    ip = Column(String(64))
    device = Column(String(200))
    sent_at = Column(DateTime, default=_now)
    first_open_at = Column(DateTime)
    confirmed_at = Column(DateTime)
    signed_at = Column(DateTime)
    reminded_at = Column(DateTime)                          # 2 工作日提醒已发
    receipt_path = Column(String(300))                     # B:确认回执 PDF
    signed_pdf_path = Column(String(300))                  # C:已签署版 PDF(原文+填写页+签署页)
    form_answers = Column(Text)                             # v4.9 5.7:员工填写字段答案 JSON {key:value}
    final_pdf_path = Column(String(300))                   # v4.9 5.7:合成后的最终文档(正文+填写页),供下载
    manual_upload_path = Column(String(300))               # v4.9 5.9:纸质回传件路径(待核验)
    manual_status = Column(String(16))                     # v4.9 5.9:pending_validation / manuscrita / rejected



class EmpDocTemplate(Base):
    """文件模板(v3.6 第七部分)。每个 doc_type 下多行=多版本;正文为受限 HTML(标题/段落/加粗/列表/表格)+
    {{变量}} 占位。发布后只读保留;已推送的文件引用当时版本、不随模板改动重渲染(7.3 红线)。"""
    __tablename__ = "empdoc_template"
    id = Column(Integer, primary_key=True)
    doc_type_id = Column(Integer, ForeignKey("empdoc_type.id"), index=True)
    name_es = Column(String(200))                            # documento_nombre(渲染时用)
    version = Column(String(32))                             # 人工填,同类型下不重复
    body_html = Column(Text)                                 # 受限 HTML 正文(含 {{变量}} 与 [FIRMA] 标记)
    form_json = Column(Text)                                 # 5.7 员工填写字段 schema(JSON;本期可空)
    firma_empresa = Column(Boolean, default=False)           # 正文是否已插入公司签名([FIRMA] 标记 → 签署页 [FIRMA_EMPRESA] 置真)
    status = Column(String(12), default="draft")             # draft 草稿 / published 已发布 / retired 已停用
    created_by = Column(Integer, ForeignKey("user.id"))
    published_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    published_at = Column(DateTime)
    __table_args__ = (Index("ix_emptpl_type_ver", "doc_type_id", "version"),)



class EmpDocSetting(Base):
    """员工文件·设置里的全公司固定值(v3.6 7.4-bis:convenio/importe_*/hora_*;及公司签名图片路径)。key 唯一。"""
    __tablename__ = "empdoc_setting"
    id = Column(Integer, primary_key=True)
    skey = Column(String(48), unique=True, index=True)
    sval = Column(Text)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class EmpDocExtField(Base):
    """员工档案·员工文件扩展字段【定义】(v4.9 7.4-ter:HR 可自助新增)。
    fkey=渲染变量名 {{fkey}};ftype=text/textarea/select/date/bool;options_json=[{code,es,zh}]。
    builtin=种子字段(附件一/通勤条款,可改选项、不可删)。"""
    __tablename__ = "empdoc_ext_field"
    id = Column(Integer, primary_key=True)
    fkey = Column(String(48), unique=True, index=True)
    label_zh = Column(String(120))
    ftype = Column(String(16), default="text")
    options_json = Column(Text)
    required = Column(Boolean, default=False)
    sort = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    builtin = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class EmpDocExtValue(Base):
    """每员工的扩展字段取值(v4.9 7.4-ter:HR 在员工档案「员工文件扩展信息」里录入)。"""
    __tablename__ = "empdoc_ext_value"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employee.id"), index=True)
    fkey = Column(String(48), index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("employee_id", "fkey", name="uq_empext_emp_field"),)



class EmpDocExtChange(Base):
    """v4.9 7.4-ter.2:员工档案扩展字段变更审计(尤其 anexo1_*→需重签附件一)。留痕不可删。"""
    __tablename__ = "empdoc_ext_change"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, index=True)
    fkey = Column(String(48))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_by = Column(Integer)
    changed_at = Column(DateTime, default=_now)



class EmpDocConsulta(Base):
    """v4.9 5.6:员工对某份文件发起「联系人事咨询」(数据有误/对内容有疑问/其他)。文件转 En revisión。"""
    __tablename__ = "empdoc_consulta"
    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, index=True)
    employee_id = Column(Integer, index=True)
    reason = Column(String(32))                              # datos_incorrectos / dudas_contenido / otro
    note = Column(Text)
    status = Column(String(16), default="open")             # open / resuelto
    created_at = Column(DateTime, default=_now)



class EmpDocOtp(Base):
    """签署验证码(按 包×员工 一份,含 C 才发)。6 位,5 分钟,连错 5 次锁定。"""
    __tablename__ = "empdoc_otp"
    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, ForeignKey("empdoc_package.id"), index=True)
    employee_id = Column(Integer, ForeignKey("employee.id"), index=True)
    code = Column(String(6))
    sent_at = Column(DateTime, default=_now)
    expires_at = Column(DateTime)
    attempts = Column(Integer, default=0)
    locked = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    aids = Column(Text)   # v4.9 #7 部分签署:本次验证码覆盖的 assignment id 列表(JSON);空=整包(旧行为)
    __table_args__ = (Index("ix_empotp_pkg_emp", "package_id", "employee_id"),)



class EmpDocLog(Base):
    """员工文件全操作留痕(append-only,存 ≥4 年)。每次操作一行。"""
    __tablename__ = "empdoc_log"
    id = Column(Integer, primary_key=True)
    package_id = Column(Integer, index=True)
    assignment_id = Column(Integer, index=True)
    employee_id = Column(Integer, index=True)
    actor_user_id = Column(Integer)                         # 操作账号(推送/导出/重置);员工自助操作记员工侧
    action = Column(String(24))                            # push/open/confirm/sign/otp_sent/otp_ok/otp_fail/remind/export/reset/new_version
    detail = Column(String(400))
    ip = Column(String(64))
    device = Column(String(200))
    created_at = Column(DateTime, default=_now, index=True)
