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
3. `v3-build.yml` 联合构建两类镜像，在合成旧库上执行真实候选迁移、重复执行、新旧程序读写和快照恢复演练。证据通过后发布 `system-ci-<run_id>-<attempt>`。v2 发行附件包括 `system-release.json`、`system-release.sig`、`v3.json`、联合镜像包、`database-migrations.json` 和 `database-compatibility.json`。完整附件发布后，CI 原子推进 `updates/v3-migrations` 分支的签名目录。
4. 保持发行附件与批次不可覆盖。目录有效期为三十天。无签名 secret 时，原有镜像交付链继续执行。

v1 的 `updates/v3` 保持原发行格式并续签三十天有效期。新通道首发承接旧发行引用。每次 CI 对受支持的最近八个来源执行演练，来源清单摘要、实际镜像配置摘要和目标迁移合同一起绑定到签名发行。证据失败会阻断签名发布。

两库合同来自固定迁移登记。普通查询、日志及页面修改保持合同稳定。登记字段为 `id/version/predecessor/checksum/engine/kind/rollback_mode`，当前初始版本为 1。已发布迁移定义及校验和保持不可变。新增建表、补列、索引和回填应增加顺序迁移及固定执行实现，并经 CI 兼容演练。`verify_database_definitions.py` 检查数据库定义所有权和登记摘要。未知及破坏性迁移沿专项维护处理。

## 首次接入底座

首次接入是一次维护部署。当前暂停中的生产部署继续等待明确上线指令。以下命令中的配置、目录、公钥和版本由执行前的上线单固定。

前提：Linux amd64、Docker Compose、Python 3、OpenSSL。部署配置及更新状态归 root 所有；目录使用 0700，私有文件使用 0600。更新目录需要位于本地持久文件系统。目录路径应足够短，以容纳 Unix socket。

1. 获取同批签名发行附件和镜像，复用原部署 SOP 核对签名、精确来源、资源和数据归属。先保存原有账号状态、角色归属及内核选择。既有资源参数继续沿用。日常升级采用本次确认的双库自动快照策略。
2. 预览接入计划。`--release-dir` 中包含已签名清单、签名及原始 `v3.json`。v2 发行还需上述两项迁移附件。准备镜像时使用同一发行的 registry digest 或经过校验的镜像包。

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

## 已安装 v1 底座接入迁移能力

此操作在每个原 v1 宿主执行一次。执行前按上线授权固定源码版本和精确文件 SHA、部署策略路径及 systemd 服务名。工具默认预览：

```bash
python3 deploy/v3/upgrade_system_updater.py \
  --policy /srv/example/updates/policy.json \
  --source-root /srv/example/reviewed-source \
  --service vibebench-updater-example.service
```

复核计划后追加 `--apply`。工具要求门禁空闲、原操作已结束、服务归属匹配，随后保存固定源码、原策略及原状态副本，停止该独立服务并获取服务锁和存储锁。它仅更换固定源码，将策略能力切至 v2 并重置新通道检查记录。实际 Unix socket 返回迁移能力、原当前版本和原 revision 后完成接入。原安装历史、账号数据和 epoch 保持原归属。失败按已保存副本恢复；后来操作进入时保护现场并记录对账状态。

进程中断会留下 `updater-upgrades/<UUID>/upgrade.json`。未完成记录会阻止新接入。使用同一已核验源码入口按原 UUID 预览恢复，服务 inactive 时也可执行：

```bash
python3 deploy/v3/upgrade_system_updater.py \
  --policy /srv/example/updates/policy.json \
  --service vibebench-updater-example.service \
  --recover <原接入UUID>
```

复核精确副本后追加 `--apply`。恢复核对全部原/新源码摘要、策略与状态、空闲门禁及服务归属，获取独立接入锁、服务锁及存储锁，再恢复原文件并启动原服务。恢复自身中断时继续使用原 UUID。后来操作、外来源码及后续接入记录触发现场保护。恢复完成以原接口的版本、revision、部署及能力验收为准。

成功后到 `/updates` 检查新通道并安装。底座及受信 Compose 模板后续变更继续采用独立运维流程。

## 自动迁移及数据保护

日常升级按“准备下载 → 排空 → 停止两个控制服务 → 双库快照 → 离线迁移 → 切换验收 → 开放准入 → 清理”执行。页面显示快照大小、每库目标版本和完成状态。离线容器固定入口、精确镜像和单库挂载，关闭网络并限制资源。

快照仅包含 `bench/db.sqlite`、`gateway/gateway.sqlite` 和操作元数据，覆盖 WAL 已提交事务。工作区和账号 HOME 沿原挂载管理。操作目录为 0700，快照为 0600。空间预算包括逻辑页、WAL、快照、恢复暂存及 64 MiB 余量。空间不足时保持原版并显示需求。

快照存于 `operations/<operation_id>/database-snapshot`。默认保留最近两组已完成快照，同时保护活动与待恢复引用。只有归属和完整性校验通过的精确文件可被轮换。异常目录保留供对账。

安装失败且尚未开放准入时，执行器关闭门禁、停止本操作维护进程，按同一组快照逐库恢复，再恢复原程序。持久恢复意图支持替换及暂存复制中断续接。两库恢复完成边界先于原程序启动，重启后继续原程序验收。

账号已经重建时，恢复前冻结本操作的环境代次和角色登记。恢复业务数据后，以精确原值和续接值核对登记，再由原运行时收口候选角色。身份、凭据和业务记录按快照恢复。外来环境变化保持维护等待。

执行器在开放准入前先持久保存 `release_started`。到达该边界后，旧快照禁止覆盖当前数据库。安装成功后的显式回退保留后来业务写入，使用已演练的旧程序兼容路径。

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

页面显示“兼容验证待补齐”时，按具体来源证据缺口核对发布材料。管理员可在新发行补齐演练后重新检查更新。发行命令和宿主策略由固定执行器控制。

## 本地隔离验证

```bash
.venv/bin/python -m unittest discover -s deploy/v3 -p 'test_system_*.py'
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p 'test_system_update*.py'
python3 deploy/v3/verify_system_update_browser.py --output .deploy/platform-online-update/browser
.venv/bin/python deploy/v3/verify_system_update.py --output .deploy/platform-online-update/docker \
  --gateway-binary .deploy/platform-online-update/bookworm-binaries/claude-code-gateway \
  --sender-binary .deploy/platform-online-update/bookworm-binaries/account-sender
```

迁移链路另加 `--migration-manifest <当前本地候选联合清单>`，并使用已有的 `v3-verify-native-warm-20261112` 两类真实旧镜像。该模式覆盖合成签名历史、真实旧库→候选→旧程序、v1 底座接入、双库部分迁移掉电、健康失败恢复、显式回退及后来数据保持。所有派生镜像仅供隔离验证。

Docker 验收入口依赖本机已有的 `v3-verify-kernel-online-final` 两类隔离底座及当前编译二进制。二进制需沿 `images/v3/Dockerfile` 的 Rust Bookworm 阶段及 `v3-verification` 特性构建；可从其 `verification-control` 和 `verification-account` 镜像分别提取 `/app/claude-code-gateway` 与 `/usr/local/bin/account-sender`。Bookworm 的 libc 与账号底座对应，宿主编译产物需单独核验运行兼容性。上例路径为本次验证实际导出的文件位置。

验收脚本派生带专属测试标签的本地镜像，使用随机部署、独立临时数据根和合成密钥。每个实际切换及恢复结果写入脱敏报告；最后按本次标签精确清理。浏览器报告使用真实构建页面和合成 API。所有场景的真实付费模型调用为零。
