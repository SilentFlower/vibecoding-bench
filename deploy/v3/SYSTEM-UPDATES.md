# 平台系统更新

管理员通过统一后台的“系统更新”页面检查发行、安装及回退。默认每六小时检查一次，安装由管理员明确点击。下载阶段继续接单；切换阶段先暂停新工作，等待已有 API、CLI、Pi、评审和凭据活动结束。

## 发布端一次性配置

1. 在受控运维环境生成独立 Ed25519 密钥。平台签名密钥与请求内核签名密钥分别管理。

   ```bash
   umask 077
   openssl genpkey -algorithm ED25519 -out platform-release-private.pem
   openssl pkey -in platform-release-private.pem -pubout -outform DER -out platform-release-public.der
   python3 -c "from pathlib import Path; print(Path('platform-release-public.der').read_bytes()[-32:].hex())"
   ```

2. 将完整 PEM 私钥配置为仓库 Actions secret `V3_SYSTEM_RELEASE_PRIVATE_KEY`。宿主仅安装上述 64 字符公钥。密钥配置由运维单独执行。
3. `v3-build.yml` 联合构建并发布两类镜像，通过验证后发布 `system-ci-<run_id>-<attempt>`。发行附件包含 `system-release.json`、`system-release.sig`、`v3.json` 和联合镜像包。完整附件发布后，CI 原子推进 `updates/v3` 分支的签名目录。
4. 保持发行附件与批次不可覆盖。目录有效期为三十天。无签名 secret 时，原有镜像交付链继续执行。

`system-update-policy.json` 默认只允许自身数据合同。数据库迁移源码变化时，需要先验证旧程序能读写迁移后的数据，再显式加入已验证的旧合同摘要。不可逆迁移通过专项维护流程执行。兼容声明属于代码审查范围。

## 首次接入底座

首次接入是一次维护部署。当前暂停中的生产部署继续等待明确上线指令。以下命令中的配置、目录、公钥和版本由执行前的上线单固定。

前提：Linux amd64、Docker Compose、Python 3、OpenSSL。部署配置及更新状态归 root 所有；目录使用 0700，私有文件使用 0600。更新目录需要位于本地持久文件系统。目录路径应足够短，以容纳 Unix socket。

1. 获取同批签名发行附件和镜像，复用原部署 SOP 核对签名、精确来源、资源和数据归属。先保存原有账号状态、角色归属及内核选择。US 沿用既有资源参数和免备份选择。
2. 预览接入计划。`--release-dir` 中包含已签名清单、签名及原始 `v3.json`。准备镜像时使用同一发行的 registry digest 或经过校验的镜像包。

   ```bash
   python3 deploy/v3/install_system_updater.py prepare \
     --env /srv/example/v3.env \
     --release-dir /srv/example/release \
     --state-root /srv/example/updates \
     --public-key <64字符平台公钥>
   ```

3. 同一命令追加 `--apply`，生成固定源码包、受信模板、私有令牌、维护门禁、`bootstrap.env` 和 systemd 单元。该步骤返回 `prepared`。
4. 按原部署 SOP 暂停入口、排空原工作。旧账号角色采用原运行时的受控停止和移除流程，保留环境行、HOME、画像、资源、凭据归属和内核数据。首次版本来源记录由新镜像重新创建角色时建立。旧角色尚存且缺少来源证明时，最终核验会要求对账。
5. 使用新底座和生成的候选配置启动两个控制服务。持久门禁保持关闭。

   ```bash
   docker compose --env-file /srv/example/updates/bootstrap.env \
     -f /srv/example/updates/source/deploy/v3/compose.yml \
     -f /srv/example/updates/source/deploy/v3/compose-updates.yml up -d
   python3 deploy/v3/install_system_updater.py finalize \
     --policy /srv/example/updates/policy.json
   ```

6. 核对预览结果后，同一 `finalize` 命令追加 `--apply`。它按配置 CAS 提交底座、校验身份及排空事实，再释放本次维护门禁。按上线单恢复原本需要运行的账号环境。逐项核对原身份、资源、内核与新来源记录。
   状态提交后或门禁释放后中断时，可重试同一 `finalize`。工具核对原发行、revision、epoch 和现场配置，继续本次收口。`--apply` 与独立执行器共用服务锁；补交首次接入前先停止已经运行的更新服务。后来安装或外来门禁按独立操作对账。
7. 安装独立服务。服务名应包含本部署标识。

   ```bash
   install -m 600 /srv/example/updates/vibebench-updater.service \
     /etc/systemd/system/vibebench-updater-example.service
   systemctl daemon-reload
   systemctl enable --now vibebench-updater-example.service
   ```

8. 在统一后台打开 `/updates`，确认当前平台和账号来源，点击“检查更新”。当前底座是最早可在线回退的版本。更早版本采用专项维护。

更新服务在宿主独立运行，使用固定部署策略。两个控制服务只读共享门禁目录；调度器额外访问私有 Unix socket。管理员请求沿网关会话鉴权和内部服务鉴权转发。浏览器请求只包含冻结版本信息。

## 日常安装与回退

- 点击“检查更新”，查看变更范围、账号镜像是否变化及数据兼容结果。
- 安装确认冻结发行、清单 SHA256、当前 revision、操作 UUID 和排空期限。默认十五分钟，可选一至一百二十分钟。
- 仅控制服务变化且账号内容兼容时，保留账号容器 ID 和环境代次。账号内容变化时，维护窗口内逐个重建原本运行的环境。原本停止或退休的环境保留状态。
- 准备和等待阶段可以取消。进入切换后按持久操作恢复。排空超时安全恢复原版准入；不确定现场保留维护状态并显示对账原因。
- 切换期间页面会短暂断线，重连后继续显示原操作。重复提交同一冻结请求返回原结果。409 表示现场已变化，需要重新查看后确认。
- 历史记录提供当前数据许可的回退目标。显式回退执行同一排空、切换及验收流程。
- 目录过期时先检查更新。已验证安装历史保留独立回退能力。

## 异常与恢复

执行器重启后读取原阶段和实际容器。切换前中断保留原版；切换后核对本次候选与原版后恢复；已经持久提交的版本完成验收及清理。更新服务通过 systemd 自动重启。

页面显示 `reconcile` 时，先核对 systemd 状态、当前操作、双端门禁 epoch、实际控制镜像和部署配置。通过页面“恢复原操作”继续同一持久操作。外部配置漂移、未知容器、外来租约和身份变化需要人工对账。门禁文件由独立服务按原操作身份管理。

清理失败显示 `succeeded_cleanup_pending`，当前版本继续服务。恢复操作可重试清理。回收保护当前组合、最近两个完整历史组合、全部容器引用及原恢复依赖。内核制品沿用已有内核生命周期管理。

更新服务自身与受信 Compose 模板采用专项运维升级。发行无法携带任意命令或替换宿主策略。

## 本地隔离验证

```bash
.venv/bin/python -m unittest discover -s deploy/v3 -p 'test_system_*.py'
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p 'test_system_update*.py'
python3 deploy/v3/verify_system_update_browser.py --output .deploy/platform-online-update/browser
.venv/bin/python deploy/v3/verify_system_update.py --output .deploy/platform-online-update/docker \
  --gateway-binary .deploy/platform-online-update/bookworm-binaries/claude-code-gateway \
  --sender-binary .deploy/platform-online-update/bookworm-binaries/account-sender
```

Docker 验收入口依赖本机已有的 `v3-verify-kernel-online-final` 两类隔离底座及当前编译二进制。二进制需沿 `images/v3/Dockerfile` 的 Rust Bookworm 阶段及 `v3-verification` 特性构建；可从其 `verification-control` 和 `verification-account` 镜像分别提取 `/app/claude-code-gateway` 与 `/usr/local/bin/account-sender`。Bookworm 的 libc 与账号底座对应，宿主编译产物需单独核验运行兼容性。上例路径为本次验证实际导出的文件位置。

验收脚本派生带专属测试标签的本地镜像，使用随机部署、独立临时数据根和合成密钥。每个实际切换及恢复结果写入脱敏报告；最后按本次标签精确清理。浏览器报告使用真实构建页面和合成 API。所有场景的真实付费模型调用为零。
