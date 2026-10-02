# 项目状态和入口

- 仓库：git@github.com:ShawnL1110/hr.git（GitHub 私有项目权限由所有者授予）。
- 目标入口：https://hr.newtonfin.com；stuff：https://stuff.newtonfin.com。
- 主机：35.42.59.31，与 finance、stuff 同机；目录 `/opt/hr`，容器 `hr-app`，独立卷 `hr_hr-data`。
- Python 3.12、FastAPI、SQLAlchemy、SQLite；锁定依赖见 `requirements.txt`。
- 本地测试：`python -m unittest discover -s tests -v`。先在虚拟环境安装 requirements；本地不要使用生产数据或生产 SSO 密钥。
- `compose.yaml` 针对共享生产网络，不能直接当作本地开发配置；本地可用 uvicorn 和测试中的合成数据、模拟身份服务，保留独立配置。

## 核实时间：2026-10-02

运行实现提交 `0c7bc0b`，部署说明提交 `2123161`；首次上线安排在该日马德里14:00（UTC12:00）。制作此 skill 时服务镜像和数据已准备，SSO 与 Caddy 尚未正式启用。接手时必须检查之后的提交、部署记录和实际站点，不得把此快照当成当前线上状态。

已经完成：独立服务、SSO 客户端/提供端、受权限限制的档案/合同下载/请假/出勤只读页面、导出导入和附件核对、请假计算模块、薪酬对账工具。39项测试在待发布镜像通过。

已导入：32张表、40员工、107附件引用/106文件。当前是一次性快照，没有自动同步；stuff 是写入事实源。历史一条考勤操作人用户名映射到已有用户ID，原值与映射在 `hr_import_notes`，原始备份未变。

尚未完成：HR 业务写入、合同签署完整流程、招聘流程、工资计算页面与完整薪酬迁移、版本化数据迁移机制、业务模块单写切换、生产发布通道正式激活（限定入口已随本次交接准备）。不能宣称全套 HR 已迁完。

## 代码导航

- `hr/main.py`：SSO、会话、主页、注销；`hr/session.py`：独立服务端会话。
- `hr/portal.py`、`hr/static/`：只读页面/API、员工范围与下载权限。
- `hr/models.py`：HR模型及少量业务身份/事实投影；`hr/leave.py`：提取的请假逻辑。
- `hr/migration.py`、`hr/import_bundle.py`、`hr/attachments.py`：白名单导出、导入、仅按HR引用复制附件。
- `hr/reconcile.py`、`tools/capture_payroll_baseline.py`：工资基线和逐项对账。
- `integrations/stuff/`：独立提交至 stuff 的 SSO 提供端参考，非 HR 自行发布范围。
- `docs/source-inventory.json`、`docs/extracted-sources.json`：源结构/提取版本证据。
- `docs/implementation.md`：剩余工作；`docs/pilot.md`：试运行限制；`docs/sso.md`：登录契约；`docs/shared-host-deployment.md`：部署/导入说明。

后续建议按模块推进：完善只读试运行与权限管理 → 档案/请假独立写入 → 合同/签署审计 → 招聘 → 薪酬输入接口与完整周期对账 → 各模块正式切换。每步都明确数据新鲜度和写入归属。
