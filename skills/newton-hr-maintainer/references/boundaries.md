# 接口与数据边界

## 归属

HR：人员档案、合同原件和签署证据、招聘、请假、审批后的出勤、薪资政策/计算/冻结工资单。
stuff：账户密码和生命周期、业务组织与案件分配、客户对话、电话/WA、原始上线活动、质检及回款事实。
HR 给 stuff 提供人工成本结果；stuff 给 HR 提供受限、版本化的薪酬输入。相关业务 API 尚未完整实现，不能将共享可写数据库当作替代。

上线活跃时间不是审批出勤；提取工资引擎时先保持原算法，新的请假扣薪策略单独评审。已确认工资改正应追加可追溯修订，不能静默覆盖。合同原件、哈希、回执、签署审计须保留；旧 OTP 不迁为可用挑战。

## SSO 契约

提供端 `https://stuff.newtonfin.com/api/hr-sso/`：GET authorize，POST token/introspect/revoke。
固定 client_id=`newton-hr`、回调=`https://hr.newtonfin.com/auth/callback`，S256 PKCE、随机state；code单次使用/60秒，opaque token八小时。后端 Bearer 仅使用专用 HR_SSO_CLIENT_SECRET，不是 stuff 的 SECRET_KEY。

introspect 只返回 active/sub/username/employee_id。每次受保护 HR 请求检查实时账户状态/会话版本，验证失败关闭访问。HR 使用 host-only Secure/HttpOnly/SameSite=Lax 的独立cookie，不共享父域cookie，不复制密码哈希。

HR_ADMIN_SUBJECTS/HR_PROFILE_SUBJECTS/HR_LEAVE_SUBJECTS/HR_DOCUMENT_SUBJECTS 填 **stuff User ID**，不是 Employee ID。权限独立，不从 stuff 管理员角色自动继承。初始仅所有者账户 User 1 配为 HR 管理员，其他账号默认只能看本人。新增团队权限要以明确成员及职责为依据，不能给全部开发者真实员工和薪资访问权。

## 数据迁移

平台维护方从一致备份导出白名单 HR bundle，不把整份 collection.db 交给 HR 团队。导入新数据库、检查完整性/外键/行数/哈希；禁止覆盖现有 HR DB。附件只复制明确引用的HR文件。生产数据不得放入Git或共享开发样本。

切换写入前：核验源版本、最终增量、接口、访问权限、工资/合同证据，再关闭旧模块写入并切换入口。切换后回滚必须处理 HR 新产生的数据，不能仅恢复旧镜像。测试和试运行证据不等于批准业务切换。
