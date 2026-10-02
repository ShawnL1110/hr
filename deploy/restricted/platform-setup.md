# 平台维护方：HR限定发布通道

该目录由平台方安装，HR代码发布不能更改此策略。普通HR成员仅持hr-deploy专用SSH密钥，不获得ubuntu/root私钥。

- `/usr/local/sbin/newton-hr-release`：root拥有的hr_release.py，755，固定命令status/logs/release SHA。
- `/etc/newton-hr-deploy/compose.json`：本目录compose.json，root600，固定镜像别名、HR卷、非root用户、资源上限、HR专属网络，不采用上传的compose/Dockerfile。
- requirements.txt：平台已审核的依赖；runtime-image：已建HR基础镜像的不可变sha256 ID。改变依赖/策略要平台评审；日常HR Python/页面功能可直接发布。
- `hr_frontend`专用Docker网络只接HR和共享Caddy，不把HR放到兄弟应用共享网络。
- hr-deploy用户无Docker组；专用authorized_keys使用restrict+强制命令，无交互shell、PTY、转发、SFTP。sudo仅允许无参数运行上述固定命令，并仅保留SSH_ORIGINAL_COMMAND供严格解析。
- `/etc/newton-hr-deploy/enabled` 默认不存在。首次上线14:00完成验证后才由平台创建；未激活时团队发布明确拒绝。

## 首次14:00上线时

确认本目录和根拥有策略安装一致。创建hr_frontend网络并把kyc-caddy-1接入（已有则不重复）；将Caddy现有Compose配置的caddy服务增加该外部网络，保留所有原网络，供以后recreate延续。此次只docker network connect+reload，不重建Caddy。不能只做临时connect却不持久化配置。

给当前HR镜像打`hr-managed:active`标签，用root策略compose启动HR：

    docker compose -p hr -f /etc/newton-hr-deploy/compose.json up -d --no-build --no-deps hr-app

SSO仍按之前的stuff增量计划接入。确认HR/TLS/真实SSO、功能权限、stuff/finance健康后，创建enabled。核验首次团队发布真实成功（使用准确已提交源码），然后更新部署记录。

## 团队命令

在HR仓库执行：

    export HR_DEPLOY_KEY=/private/path/hr_deploy.pem
    sh deploy/restricted/client.sh status
    sh deploy/restricted/client.sh logs
    sh deploy/restricted/client.sh release

先独立核验主机公钥指纹。release上传git archive HEAD，代码须先提交并推送；服务器只接受hr/、docs/及批准的requirements，拒绝链接/越界/隐藏密钥。服务器记录revision label及实际archive SHA256（标签本身不是GitHub来源证明）。团队密钥即HR代码发布授权，应按人员分发/撤销。

每次发布备份HR SQLite，健康检查失败只还原镜像，不盲目回退数据库。复杂迁移或依赖改变先在测试环境演练，由平台协同。附件持续在独立卷，代码发布不删除附件。

移除某团队密钥即可撤销发布权。未验证前不得把此入口描述为已可生产发布。
