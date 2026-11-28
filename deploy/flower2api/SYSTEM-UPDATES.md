# 平台系统更新

管理员通过统一后台的“系统更新”弹窗（侧栏版本号或 `/updates`）检查发行、安装及回退。默认每六小时检查一次，安装由管理员明确点击。下载阶段继续接单；切换阶段先暂停新工作，等待已有 API、CLI、Pi、评审和凭据活动结束。

本文仓库命令使用 `deploy/flower2api/` 源码入口。已安装更新器的固定包继续位于 `source/deploy/v3/`，由来源映射从新目录复制。systemd 启动路径、Compose 策略及服务归属检查沿既有合同。日常短入口为 `scripts/flower2api-stack`，原 `scripts/v3-stack` 兼容转发。

## 发布端一次性配置

1. 在受控运维环境生成独立 Ed25519 密钥。平台签名密钥与请求内核签名密钥分别管理。

   ```bash
   umask 077
   openssl genpkey -algorithm ED25519 -out platform-release-private.pem
   openssl pkey -in platform-release-private.pem -pubout -outform DER -out platform-release-public.der
   python3 -c "from pathlib import Path; print(Path('platform-release-public.der').read_bytes()[-32:].hex())"
   ```

2. 将完整 PEM 私钥配置为仓库 Actions secret `V3_SYSTEM_RELEASE_PRIVATE_KEY`。将同一把 64 字符公钥配置为仓库 Actions variable `V3_SYSTEM_RELEASE_PUBLIC_KEY`，用于受信候选构建的兼容演练。宿主安装同一公钥。
3. 手动运行 `v3-release.yml`，选择 v3 或 flower2api 并勾选 `publish`。流程联合构建两类镜像，在合成旧库上执行真实候选迁移、重复执行、新旧程序读写和快照恢复演练。证据通过后发布 `system-ci-<run_id>-<attempt>`。v2 发行附件包括 `system-release.json`、`system-release.sig`、`v3.json`、联合镜像包、`database-migrations.json` 和 `database-compatibility.json`。完整附件发布后，CI 原子推进 `updates/v3-migrations` 分支的签名目录。
4. 保持发行附件与批次不可覆盖。目录有效期为三十天。发布前必须配置有效 Ed25519 签名 secret，流程在构建前核验。

v1 的 `updates/v3` 保持原发行格式并续签三十天有效期。新通道首发承接旧发行引用。发行证据覆盖受支持的最近八个来源，来源清单摘要、实际镜像配置摘要和目标迁移合同一起绑定到签名发行。真实演练失败会阻断签名发布。

两库合同来自固定迁移登记。普通查询、日志及页面修改保持合同稳定。登记字段为 `id/version/predecessor/checksum/engine/kind/rollback_mode`，当前初始版本为 1。已发布迁移定义及校验和保持不可变。新增建表、补列、索引和回填应增加顺序迁移及固定执行实现，并经 CI 兼容演练。`verify_database_definitions.py` 检查数据库定义所有权和登记摘要。未知及破坏性迁移沿专项维护处理。

## 构建与手动发布

1. 日常提交到 v3/flower2api，或创建目标为这些分支的 PR，运行 `v3-build.yml`。可手动运行同一构建入口。它执行合同测试和本地镜像构建，保存 `v3-build-<run_id>-<attempt>` 清单 artifact。本仓受信分支的 push/手动构建另导出 `v3-candidate-<run_id>-<attempt>`，包含两镜像归档、原构建清单和文件摘要，保留一天。PR继续只验证和保存清单。
2. 准备正式发行时更新 `deploy/flower2api/platform-release.json`，修复递增补丁，功能递增次版本。手动运行 `v3-release.yml`，通过分支选择器选择 v3 或 flower2api，并勾选 `publish`。发布端先检查签名配置，再查找同仓、同分支、同SHA的可信候选；在途构建最多等待二十分钟。来源及归档摘要核对后复用文件层，只改为当前手动发布的 run/attempt 标签，并核对运行配置保持一致。没有候选、候选过期或原构建失败时沿原完整验证和构建路径执行；来源异常、归档篡改或等待超时保持失败。
3. 命令行等价入口：

   ```bash
   gh workflow run v3-build.yml --ref flower2api
   gh workflow run v3-release.yml --ref flower2api -f publish=true
   ```

4. 发布流程核对手动事件、工作流文件、所选分支及明确标记。签名配置提前校验，真实旧库兼容演练先于镜像推送；完整发行附件上传后才推进受信目录。发行序号从已验签的历史目录连续递增，工作流运行计数独立记录。
5. 发行完成后，由原 v3 实例管理员在“系统更新”中检查、准备和安装。仓库、镜像名、发行身份、信任根、数据合同、部署和持久数据沿既有更新链保持兼容；原 v1 底座按下节 SOP 补齐迁移能力。

### 受信候选与发布完成边界

发布侧使用 `actions:read` 读取构建来源和归档。复用仅接受 `v3-build.yml` 中合同校验、镜像构建、AGY 镜像验收、候选导出和候选上传均成功的同一 attempt。仓库、原始仓库 ID、分支、SHA、工作流路径、归档 ID 及 GitHub ZIP 摘要逐项核对。解包接受 `candidate.json`、`v3-local.json`、`candidate-images.tar.gz` 及可选的 `database-compatibility.json`。候选镜像和清单的大小与摘要继续独立核对，工作区必须保持同一干净源码。

候选构建在 AGY 镜像验收期间并行跑真实旧库兼容演练。候选上传完成即可供发布端复用，构建 job 的缓存 post 可继续后台执行。候选换批只允许修改 `vibebench.release`，文件层、平台、环境变量、启动参数和其余标签须完整一致。含 ONBUILD 触发器的镜像拒绝复用。正式发布按当前签名目录核对来源、镜像和合同。有效候选证据随换批重新绑定镜像摘要。证据缺失、演练失败或签名目录变化时，正式发布执行完整演练。线上安装验签并执行升级，演练发生在 CI。

兼容演练通过后，两路镜像推送与离线归档并行执行。任一路失败会等待其余作业退出，保留本attempt的已开始标记；全部通过后才发布完整交付清单。大镜像包只进入正式Release，Actions发行artifact保留诊断清单和兼容证据。签名发行及原子目录发布完成即具备安装条件，构建缓存的后续保存独立收尾。

候选完整性依照[GitHub产物摘要合同](https://docs.github.com/en/rest/actions/artifacts)核对原始ZIP，发行签名和原有手动入口限制继续保留。需要绕开候选等待或执行冷构建诊断时，在手动发布中选中 `full_build`，或使用 `gh workflow run v3-release.yml --ref flower2api -f publish=true -f full_build=true`；该路径重新执行完整校验、构建、兼容演练和签名。

### 构建缓存与兼容演练提速

两个 workflow 共用 `.github/actions/flower2api-build-cache`。Docker 层缓存按平台和编译产物、control、account 三个构建目标分开保存。Cargo 的 registry、git 和 target 挂载通过独立缓存恢复。缓存键包含平台、依赖配方和源码指纹，恢复前缀限定同一依赖配方。可信目标分支的 push／手动构建可以保存缓存，PR 采用只读恢复。

缓存准备失败时，工作流记录告警并沿普通 Docker 构建执行。未命中时完整构建。层缓存导入和导出各限两分钟，导出错误单独告警；实际编译、迁移或发布失败继续阻断流程。

普通本地入口沿用 `docker build`。需要显式使用已存在的 Buildx builder 时，通过进程环境设置以下可选项，部署配置文件继续使用原 `V3_*` 合同：

| 环境项 | 含义 |
| --- | --- |
| `FLOWER2API_BUILDX_BUILDER` | 具名 builder，构建后通过 `--load` 加载本地镜像 |
| `FLOWER2API_BUILD_CACHE_SCOPE` | 可选 GHA 层缓存命名空间，自动追加镜像角色 |
| `FLOWER2API_BUILD_CACHE_WRITE` | `true`／`false`，默认只读；写入还需满足受信 CI 来源 |

builder 和 scope 仅接受最长 64 字符的字母、数字、下划线、点和连字符名称，首字符须为字母或数字。GHA 鉴权由当前 job 的 runtime 环境提供。缺少缓存 runtime 环境时使用本地 builder 缓存。

`manage.py build` 默认预构建。它从同一源码快照导出 Vue、网关和发送器产物，两类镜像使用这次导出的产物封装。候选和正式发布使用同一默认路径。需要回退或做对照时，使用 `manage.py build --no-prebuilt`。冷暖缓存对照使用两个新建的 Buildx builder，每个 builder 连续跑两次，四次使用不同的 `--release` 和 `--manifest`，保持同一提交及制品，关闭共享 GHA 层缓存。对比 `flower2api-build-complete` 的总耗时、源码版本和源码摘要。预构建路径另用 `flower2api-build-precompiled` 标记编译耗时。

历史双库演练支持 `--workers 1|2|4`，默认串行，正式发布显式使用 `--workers 4`。每路分别拥有独立容器、临时目录、数据库和操作 ID，每个来源保留升级、两次迁移、新旧程序读写及快照恢复。单容器继续限制 768 MiB 内存和 128 个进程，沿用无网络、只读和最小权限参数。任一来源失败后停止排队项，等待已启动项收口，再传播带来源标记的错误。全部成功后按原来源顺序写入证据。

性能日志使用 `flower2api-build-role`、`flower2api-database-source` 和 `flower2api-database-complete` 事件；兼容证据格式保持原合同。新增 `flower2api-database-resources` 记录 Linux 主机范围的 CPU 峰值、内存可用量最低值、内存使用峰值及相对起点增量、OOM 计数增量、CPU 数和采样有效性。`scope=host` 包含 Docker 与其它进程，不能将其等同于演练进程独占资源。读取不可用时输出 `available=false`，未知值使用 null；统计仅进入性能日志，原演练错误继续传播。

测量需要分别记录缓存准备／保存、构建和演练耗时，并标明本地或 GitHub CI 条件。两路／四路对照使用同一候选及同一历史集合；合成八条历史必须注明真实镜像构成。正式 GitHub runner 的资源和实际八版本耗时由后续正式发行独立核对。临时恢复可使用 `--workers 1` 或 `--workers 2`；关闭新增缓存环境项可恢复普通 Docker 入口。

### 分支生效步骤

本轮代码在 flower2api 开发。GitHub 的 push 触发规则取自事件对应分支；v3/main 上的旧自动发布在各自同步工作流修复后生效。因此必须将构建发布修复同步到 v3，将旧 `docker-publish.yml` 的手动化修复同步到 main。默认分支当前为 main；新 `v3-release.yml` 也须在默认分支注册，才能稳定展示和触发手动入口。该工作流仍只允许 v3/flower2api 的手动发布。

同步时使用明确的提交和目标分支，并在推送前复核目标中的事件与 job 条件。当前分支文件的本地验证与远端各分支触发规则分别验收。分支同步、正式发行及生产安装各自按明确的 Git/上线授权执行。

## 账号页选择 Claude CLI 直发

从 v1.45.1 起，账号页保存的转发方式是生效内核的唯一选择。升级保留账号的当前值、待切目标及修订，新建、资料导入和重新启用沿各入口的既有默认。先通过原排空门禁在中央和各所属 SSH 节点安装同批签名 control 与 account 镜像。

活跃 Claude OAuth 账号在账号页选择“交互运行时 V2”并保存。使用 API 时，在 `PUT /admin/accounts/<网关账号ID>` 提交 `request_backend=tui_v2` 和该账号实收的 `request_backend_revision`。编排按原代理和归属环境准备同批官方 CLI。账号镜像声明的受管能力由系统提供，已有管理员策略优先。内建 `sec-default@builtin` 仍须启用。

管理接口展示当前选择、待切目标、`tui_direct_available` 和 `tui_v2_unavailable_reason`。V2 的新请求、原工具续轮和预热均要求当前 sender 与同轮预留确认直发。能力未就绪返回 503，并给出实际准备阶段。选中 V2 后只允许真实 CLI 生成模型响应，非生成元数据沿独立接口。v1.44.0 起，符合交互会话导入条件的普通 Messages 可使用结构化格式、指定工具、强制工具调用、禁止并行、带声明的 none 和非默认温度。验收仅针对用户显式选择 V2 的账号，逐笔关联公网 SSE、原代理、同一预留和一次模型投递。

v1.45.0 起，受管 V2 只承接具备完整账号凭据和直发 Mod 的请求。无法原生保留的本轮文本缓存断点、超出本轮无损粘贴范围的图片、错误工具结果中的图片、消息列表里的 system 指令以及来源无法核验的签名历史，会在投递前返回 `422` 和对应业务错误码。历史已确认图片、历史缓存标记、工具缓存声明、合法上下文管理和已核验签名按各自原生合同交付。

需要切回 V1 时，在同一账号保存“原生运行时 V1”，待原有轮及工具回执收口后确认 `native293` 生效。平台级故障使用管理更新页回退同批签名制品，按目标版本现场合同核对原账号、节点和已保存选择。

## 单部署镜像与容器名称切换

正式镜像采用 `flower2api-control/account`，控制 Compose 项目与网络采用 `flower2api-<deployment>`。账号容器采用 `flower2api-<部署哈希前12位>-<环境ID>`，保留 CLI/sender 后缀；最长 sender 名为63字节。部署 ID、持久数据目录、内部所有权标签、V3 配置键、systemd 服务名和签名发行身份沿既有合同保留。本版建立 Flower2API 正式维护基线，当前旧来源和已签材料用于首次交接及失败恢复。后续正式升级与回退从本版基线起算。

本次名称切换适用于操作者统一管理的单部署，沿同一签名通道完成一次维护。固定宿主更新器在应用镜像外持有源码和受信模板，需先按专项维护核对其精确根、源码 SHA、策略中模板摘要及服务归属，停止该独立服务并在服务锁和存储锁保护下同步已核验源码与模板。保持原策略、安装历史、revision 和 epoch 的归属；v1→v2 接入工具对已有v2返回 already-current，不能替代这次同协议源码刷新。

发布与迁移顺序：

1. 验证新包同批签名、配置/仓库/内容摘要及离线包。按既有交付要求完成包可见性和匿名拉取验收。
2. 预览当前部署的精确容器 ID、网络、数据挂载、固定源码和策略摘要，保存私有恢复材料；继续使用原维护门禁及操作日志，等待养号 CLI、API、评审和租约自然排空。
3. 更新器按已验证实际 ID 停止控制角色，创建快照。新项目创建前仅移除本操作冻结且已停止的原项目控制容器，持久挂载继续保留。
4. 新控制角色启动后，将当前登记的原账号网络角色以精确旧别名临时接入；重新核对环境、角色、镜像和来源，沿原 network-guard 入口更新新网络网关及实际控制 IP 的管理白名单，再逐项沿原环境维护入口重建。停止环境沿既有保留规则处理，后续唤醒采用新命名。
5. 验证控制及账号来源、原身份和数据、CPU/RAM策略、内核选择、原生预热及 CRIU 状态，再按原状态机开放准入。回收范围继续保护当前、最近两套完整历史及所有容器/恢复引用。

中断时先核对已完成的源码替换、容器与网络连接，按同一操作日志恢复。新旧网络的控制连接只能匹配一个受信部署网络，缺失或歧义保持拒绝。快照恢复继续服从 `release_started` 边界，开放后保留后来业务写入；历史发行附件保持原签名字节。

首次迁移可能需要恢复旧程序，旧程序只读取旧包来源。失败恢复时，已登记的新来源角色先由候选程序逐项收口，持久登记原代次、允许镜像和 CPU，保留账号记录与 HOME，再由旧程序重建；部分角色继续逐项核验实际进程、租约和允许镜像，未知归属保持维护关闭。账号内容相同而仓库族变化时也需要重建，保证来源与命名同步迁移。历史旧版本主动回退保障退出本次交付范围。

## 首次接入底座

首次接入是一次维护部署。当前暂停中的生产部署继续等待明确上线指令。以下命令中的配置、目录、公钥和版本由执行前的上线单固定。

前提：Linux amd64、Docker Compose、Python 3、OpenSSL。部署配置及更新状态归 root 所有；目录使用 0700，私有文件使用 0600。更新目录需要位于本地持久文件系统。目录路径应足够短，以容纳 Unix socket。

1. 获取同批签名发行附件和镜像，复用原部署 SOP 核对签名、精确来源、资源和数据归属。先保存原有账号状态、角色归属及内核选择。既有资源参数继续沿用。日常升级采用本次确认的双库自动快照策略。
2. 预览接入计划。`--release-dir` 中包含已签名清单、签名及原始 `v3.json`。v2 发行还需上述两项迁移附件。准备镜像时使用同一发行的 registry digest 或经过校验的镜像包。

   ```bash
   python3 deploy/flower2api/install_system_updater.py prepare \
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
   python3 deploy/flower2api/install_system_updater.py finalize \
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
python3 deploy/flower2api/upgrade_system_updater.py \
  --policy /srv/example/updates/policy.json \
  --source-root /srv/example/reviewed-source \
  --service vibebench-updater-example.service
```

复核计划后追加 `--apply`。工具要求门禁空闲、原操作已结束、服务归属匹配，随后保存固定源码、原策略及原状态副本，停止该独立服务并获取服务锁和存储锁。它仅更换固定源码，将策略能力切至 v2 并重置新通道检查记录。实际 Unix socket 返回迁移能力、原当前版本和原 revision 后完成接入。原安装历史、账号数据和 epoch 保持原归属。失败按已保存副本恢复；后来操作进入时保护现场并记录对账状态。

进程中断会留下 `updater-upgrades/<UUID>/upgrade.json`。未完成记录会阻止新接入。使用同一已核验源码入口按原 UUID 预览恢复，服务 inactive 时也可执行：

```bash
python3 deploy/flower2api/upgrade_system_updater.py \
  --policy /srv/example/updates/policy.json \
  --service vibebench-updater-example.service \
  --recover <原接入UUID>
```

复核精确副本后追加 `--apply`。恢复核对全部原/新源码摘要、策略与状态、空闲门禁及服务归属，获取独立接入锁、服务锁及存储锁，再恢复原文件并启动原服务。恢复自身中断时继续使用原 UUID。后来操作、外来源码及后续接入记录触发现场保护。恢复完成以原接口的版本、revision、部署及能力验收为准。

成功后到 `/updates` 检查新通道并安装。底座及受信 Compose 模板后续变更继续采用独立运维流程。

## 自动迁移及数据保护

日常升级按“准备下载 → 排空 → 停止两个控制服务 → 双库快照 → 离线迁移 → 切换验收 → 开放准入 → 清理”执行。弹窗的进度列表逐步显示各阶段与进入时间，操作详情显示快照大小、每库目标版本和完成状态。离线容器固定入口、精确镜像和单库挂载，关闭网络并限制资源。

快照仅包含 `bench/db.sqlite`、`gateway/gateway.sqlite` 和操作元数据，覆盖 WAL 已提交事务。工作区和账号 HOME 沿原挂载管理。操作目录为 0700，快照为 0600。空间预算包括逻辑页、WAL、快照、恢复暂存及 64 MiB 余量。空间不足时保持原版并显示需求。

快照存于 `operations/<operation_id>/database-snapshot`。默认保留最近两组已完成快照，同时保护活动与待恢复引用。只有归属和完整性校验通过的精确文件可被轮换。异常目录保留供对账。

安装失败且尚未开放准入时，执行器关闭门禁、停止本操作维护进程，按同一组快照逐库恢复，再恢复原程序。持久恢复意图支持替换及暂存复制中断续接。两库恢复完成边界先于原程序启动，重启后继续原程序验收。

账号已经重建时，恢复前冻结本操作的环境代次和角色登记。恢复业务数据后，以精确原值和续接值核对登记，再由原运行时收口候选角色。身份、凭据和业务记录按快照恢复。外来环境变化保持维护等待。

执行器在开放准入前先持久保存 `release_started`。到达该边界后，旧快照禁止覆盖当前数据库。安装成功后的显式回退保留后来业务写入，使用已演练的旧程序兼容路径。

## CLI 临时文件磁盘布局首次接入

1. 先按同协议宿主源码刷新边界核验独立执行器：固定安装根、原/新源码SHA256、服务归属及idle门禁，停止独立服务后备份并更新`system_update_contract.py`、`system_updater.py`和`system_update_host.py`，重启后核对原安装状态、签名目录与能力拒绝行为。当前已是v2的安装继续使用同协议刷新流程。
2. 先安装声明`scratchpad_storage=1`的兼容发行。该阶段保持账号组件内容摘要与原发行一致，沿原选择复用账号镜像、角色ID及generation；管理端具备恢复磁盘布局的能力。
3. 兼容阶段完成验收后，再安装同时声明`scratchpad_activation=1`的启用发行。声明来自实际控制/账号镜像的构建记录，跳过兼容阶段的安装会在宿主动作前拒绝。
4. 启用后的回退目标必须声明`scratchpad_storage=1`。兼容管理端依据已保存的账号数据建立原路径挂载，并可配合原账号镜像继续历史会话。缺少恢复能力的旧版在列表、回退准入和宿主失败恢复中受保护。
5. 两阶段分别沿原签名发行与安装操作验收。回退验收核对真实CLI原session、原路径文件、最新HOME及账号归属，sender性能按固定版本和负载比较。

## V2 工具回执恢复首次接入

- 已有 v2 固定宿主先执行同协议源码刷新。以候选签名发行关联的精确提交为新源码，从该提交的 `deploy/flower2api/system_update_host.py` 和 `deploy/flower2api/system_updater.py` 分别复制到原固定安装根的 `source/deploy/v3/` 同名位置。先按实际部署核对原服务的 `ExecStart`、当前发行、revision、策略和受信模板摘要。混合历史底座按实际文件计算旧 SHA256，候选逐个计算新 SHA256。
- 在独立服务空闲且维护门禁为 `idle` 时备份原文件，停止该服务并按原服务锁和存储锁范围替换。复核摘要并从固定目录用 `python3 -I` 验证加载，再启动原服务。复核原安装状态、revision、空闲门禁和签名更新目录。替换、加载或重启失败时恢复原文件并重新启动原服务。
- 用原系统更新入口安装签名候选。若旧网关带有待回执，宿主保留账号运行环境，等待同一维护代次的实际活动排空，再按原路径核对双库快照、切换中央与开放准入。新版网关可关闭无关推理，等待已接纳的 V2 工具续轮及已开始交付工具的响应收尾。具备账号滚动能力时，待回执或节点失联由原账号独立延期；需要重建原环境的安装与回退继续核对原回执。
- 系统更新页的「核对并恢复」立即检查单条原回执。原进程已确认退出后收口该回执，账号后台换版随后续办。旧 sender 使用账号整体空闲证明。新版 sender 支持单轮核对，同账号的其他会话可以继续等待工具。显示「该账号延期、平台可继续」时，恢复节点连接后可再次点击，后台也会自动重试。

## 日常安装与回退

- 点击“检查更新”，查看变更范围、账号镜像是否变化及数据兼容结果。
- 点击“下载更新”，当前版本继续服务。下载及校验完成后，宿主保存待重启回执。刷新管理页或更新器重启后仍可继续。点击“立即重启”前再次核对本地材料。材料失效时重新下载。
- 声明 `vibebench.project-library-prepare=1` 的控制镜像在准备阶段校验并注册项目库。进度显示“后台准备候选镜像与项目库”时，原版本继续接单。切换后调度器直接读取本次候选的冻结目录。
- 已安装更新器按同协议源码刷新流程同步 `system_update_contract.py`、`system_update_rollout.py`、`system_update_host.py`、`system_updater.py` 和受信 Compose 模板。沿本文件的固定安装根、备份、服务和存储锁要求完成刷新。重启后核对当前发行、revision、空闲门禁及状态响应中的 `staged_updates`。
- 原版与候选均支持本机后台更新时，重启会结束剩余推理。控制服务和数据验收通过后开放全局准入，再逐个更新需要重建的本机账号。SSH 节点按节点进度独立更新。旧底座或旧控制组合沿所支持的安装方式。
- 账号内容兼容时，保留账号容器 ID 和环境代次。内容变化时，只有宿主确认精确归属、环境代次和实际镜像的旧环境可继续接单。账号占用或重建超时会显示在“账号后台更新”中，可按单项重试。原本停止、停用或关闭接单的账号保留各自设置。
- 安装确认冻结发行、清单 SHA256、当前 revision 和操作 UUID。兼容安装入口另接受排空期限，默认一分钟，可选一至一百二十分钟。
- 准备和等待阶段可以取消。进入切换后按持久操作恢复。排空超时安全恢复原版准入；不确定现场保留维护状态并显示对账原因。
- 切换期间弹窗会短暂断线并提示正在重新连接，重连后继续显示原操作。重复提交同一冻结请求返回原结果。409 表示现场已变化，需要重新查看后确认。
- 历史记录提供当前数据许可的回退目标。显式回退执行同一排空、切换及验收流程。
- 目录过期时先检查更新。已验证安装历史保留独立回退能力。

## 异常与恢复

执行器重启后读取原阶段和实际容器。切换前中断保留原版；切换后核对本次候选与原版后恢复；已经持久提交的版本完成验收及清理。更新服务通过 systemd 自动重启。

候选控制服务验收超时后，展开“操作详情与数据库快照”，分别查看网关和调度器的最后一次探测状态、已收到的 HTTP 状态码及耗时。失败回退的探测结果单独保存在同一操作下。

旧版兼容安装再次尝试时，更新器会核对上一次已恢复的宿主操作和 SSH 节点回执，再归档其已完成的节点维护记录。原节点资料、归属及仍需恢复的记录由原操作继续管理。

弹窗显示“等待恢复与对账”（`reconcile`）时，先核对 systemd 状态、当前操作、双端门禁 epoch、实际控制镜像和部署配置。通过弹窗的“恢复操作”继续同一持久操作。外部配置漂移、未知容器、外来租约和身份变化需要人工对账。门禁文件由独立服务按原操作身份管理。

清理失败显示 `succeeded_cleanup_pending`，当前版本继续服务。恢复操作可重试清理。回收保护当前组合、最近两个完整历史组合、全部容器引用及原恢复依赖。内核制品沿用已有内核生命周期管理。

弹窗显示“兼容性待核对”（版本记录中的安装按钮为“待验证兼容”）时，按具体来源证据缺口核对发布材料。管理员可在新发行补齐演练后重新检查更新。发行命令和宿主策略由固定执行器控制。

## 本地隔离验证

```bash
.venv/bin/python -m unittest discover -s deploy/flower2api -p 'test_system_*.py'
PYTHONPATH=services/orchestrator .venv/bin/python -m unittest discover -s services/orchestrator -p 'test_system_update*.py'
python3 deploy/flower2api/verify_system_update_browser.py --output .deploy/platform-online-update/browser
.venv/bin/python deploy/flower2api/verify_system_update.py --output .deploy/platform-online-update/docker \
  --gateway-binary .deploy/platform-online-update/bookworm-binaries/claude-code-gateway \
  --sender-binary .deploy/platform-online-update/bookworm-binaries/account-sender
```

迁移链路另加 `--migration-manifest <当前本地候选联合清单>`，并使用已有的 `v3-verify-native-warm-20261112` 两类真实旧镜像。该模式覆盖合成签名历史、真实旧库→候选→旧程序、v1 底座接入、双库部分迁移掉电、健康失败恢复、显式回退及后来数据保持。所有派生镜像仅供隔离验证。

Docker 验收入口依赖本机已有的 `v3-verify-kernel-online-final` 两类隔离底座及当前编译二进制。二进制需沿 `images/v3/Dockerfile` 的 Rust Bookworm 阶段及 `v3-verification` 特性构建；可从其 `verification-control` 和 `verification-account` 镜像分别提取 `/app/claude-code-gateway` 与 `/usr/local/bin/account-sender`。Bookworm 的 libc 与账号底座对应，宿主编译产物需单独核验运行兼容性。上例路径为本次验证实际导出的文件位置。

验收脚本派生带专属测试标签的本地镜像，使用随机部署、独立临时数据根和合成密钥。每个实际切换及恢复结果写入脱敏报告；最后按本次标签精确清理。浏览器报告使用真实构建的系统更新弹窗和合成 API。所有场景的真实付费模型调用为零。
