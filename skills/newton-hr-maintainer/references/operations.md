# 部署与隔离

HR 团队负责HR仓库；HR限定发布账号及根拥有策略已安装，首次14:00上线验收后激活。**以下主机操作由平台维护方执行，或在以后已配置且验证的 HR 限定发布通道内执行。**不能通过获得 Docker 组、无限 sudo、ubuntu/root 密钥来“只部署 HR”。Docker 控制权等同于主机控制权。

拓扑：唯一公网入口 kyc-caddy-1，导入 `/opt/caddy-sites/*.caddy`。HR 独立文件 `/opt/caddy-sites/hr.caddy` → hr-app:8080；HR专属网 hr_frontend（首次上线由平台方连接Caddy并持久化配置），不连接兄弟应用网络。不得发布宿主8080或另外启动反代。修改Caddy由平台方负责，仅validate+reload，不restart或覆盖总配置。

HR服务：/opt/hr/compose.yaml，卷hr_hr-data挂载/data，UID10001；只读根文件系统、tmpfs /tmp、无capability、no-new-privileges。当前限制内存256MiB、含swap384MiB、CPU0.5。不能自行放开上限，任何扩容先核容量。容器只挂载HR卷，不挂载stuff数据或宿主Docker socket。

## 发布流程

1. 检查线上版本及工作树，fetch最新代码；备份HR数据库（SQLite backup保证一致）、附件及当前镜像，并记录恢复路径。正常HR更新只需HR范围备份，不读取stuff。
2. 测试通过后commit+push。平台方发布准确提交的干净源码，排除.env/.git/private/data/虚拟环境/缓存；不上传其他人的未提交代码。
3. 只构建HR：`docker compose -f /opt/hr/compose.yaml build hr-app`，校验启动、数据版本、权限。只切换HR：`docker compose -f /opt/hr/compose.yaml up -d --no-deps --no-build hr-app`。不用compose down，不操作collection或其他容器。
4. 验证https://hr.newtonfin.com/healthz、TLS、真实SSO往返、本人/他人访问控制、附件授权和受影响功能。看HR日志时避免输出cookie、code、token和员工PII。核对stuff及finance仍可用。
5. 发布失败先恢复HR镜像；若有数据库迁移则按预演恢复/前滚方案处理，避免旧代码读取不兼容库。报告结果并更新docs中的实际状态。

共享主机的正常发布窗口避开马德里9:00–14:00。不要因此阻断日常本地开发；窗口限制针对部署。如已获本次明确时间授权按授权执行。需要修改stuff接口、登录提供端、共享代理或网络时，交给对应维护方；HR技能本身不授权这些操作。

一次性首次上线已由平台方安排2026-10-02马德里14:00，接手者不要重复触发或抢先部署。先查验是否已经完成。

## HR专用发布方式

使用私密包的hr_deploy.pem，在HR仓库执行`HR_DEPLOY_KEY=/私密路径/hr_deploy.pem sh deploy/restricted/client.sh status`；把status换成logs或release分别查看HR日志、发布已提交代码。先推送GitHub。服务器使用root固定发布策略，仅提取HR运行代码，忽略上传的Dockerfile/compose；只允许HR卷、资源上限和hr_frontend网络。依赖变更或策略变化交平台维护方。首次上线前release会被拒绝，不要绕过。详见仓库deploy/restricted/platform-setup.md。

## 权限落地建议

给每人独立GitHub访问，保护发布分支；生产部署由独立工作流/平台方完成。若以后需要SSH，仅使用各人提交的公钥和强制命令发布通道，固定仓库、服务、数据路径及资源限制，不提供通用shell/sudo/Docker组。实现前由平台方验证无法操作兄弟服务。技能约定不能替代这些操作系统权限边界。

## 上线状态更新（2026-10-02）

用户已改为立即上线，HR 独立域名和 stuff SSO 已启用。真实账号登录及业务页面由 HR 团队验收，尚未代替团队确认。当前仍为只读静态快照，stuff 继续写入。实际部署使用 `/etc/newton-hr-deploy/compose.json` 固定策略；团队日常使用 `deploy/restricted/client.sh`，不要按旧文档直接运行 `/opt/hr/compose.yaml`。原 14:00 自动部署已暂停。以 `docs/shared-host-deployment.md` 最新记录为准。

HR专用发布通道已激活并实测成功：运行版本 d401152，固定平台镜像策略已修复 BuildKit 兼容性；发布时仅重建 hr-app。真实登录和业务页面验收按用户要求交由 HR 团队完成。
