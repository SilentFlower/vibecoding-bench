# v3 独立部署

本轮交付管理和账号两个镜像。管理镜像分别启动 gateway 和 orchestrator；每账号一个固定容器，账号容器没有宿主端口。原部署不会自动迁移或切流。

```bash
python3 deploy/v3/manage.py build --release local-20261012 --manifest releases/v3-local-20261012.json
cp deploy/v3/example.env /absolute/path/v3.env
# 填写独立数据目录、两个镜像标签、清单绝对路径及至少 32 字符的密码/秘密。
chmod 600 /absolute/path/v3.env
python3 deploy/v3/manage.py check --env /absolute/path/v3.env
python3 deploy/v3/manage.py up --env /absolute/path/v3.env
python3 deploy/v3/manage.py status --env /absolute/path/v3.env
python3 deploy/v3/manage.py stop --env /absolute/path/v3.env
python3 deploy/v3/manage.py backup --env /absolute/path/v3.env --backup-dir /absolute/path/new-v3-backup
```

建议端口 18080 只是默认值，实际启动前必须空闲。默认绑定 127.0.0.1；远程访问按现有安全反代配置接入这个新端口。内部账号和调度器服务只在独立 Docker 网络通信。

每个构建批次使用唯一 `v3-<release>` 标签。清单记录父仓和子仓提交、冻结源码内容哈希、工作区是否有未提交修改、平台、默认 CLI、布局与传输版本及两个镜像的本地 ID（`digest`）与原始配置哈希（`config_digest`）；启动逐项核对标签、角色、批次和镜像身份。不得用旧 latest、混用批次或覆盖清单。本地构建不会推送镜像。`scripts/v3-stack` 提供同一组命令的短入口。

## GHCR 发布与远程交付

v3 分支的 Action 联合构建后发布两个专用包：`ghcr.io/silentflower/vibebench-v3-control` 和 `ghcr.io/silentflower/vibebench-v3-account`，统一标签 `v3-ci-<run_id>-<run_attempt>`。仅 v3 ref 的当前 Action 可以调用 publish；使用 `GITHUB_TOKEN`，不写旧版包或 latest。父提交必须对应当前 Action，未提交来源拒绝发布，同一 attempt 的发布标记禁止重试；失败重跑必须使用新 attempt。

只有两个镜像都推送成功并取得仓库 digest 后才保存发布清单。`digest` 是构建机 Docker 的本地 ID，可能指向 OCI 索引；`config_digest` 根据归档原始配置字节计算，`registry_digest` 则是推送的仓库 manifest/索引 digest。不同 Docker 存储实现的本地 ID 可以不同，启动仍必须匹配清单固定的配置或 OCI 根及相同平台。Action 的 `v3-release-<run_id>-<run_attempt>` artifact 保存发布清单、同批压缩镜像包及其 SHA256/大小，保留 14 天，不包含部署配置或账号资料。

```bash
# 从对应 Action 下载同批 artifact，先保存发布清单。
scripts/v3-stack pull --manifest /absolute/path/v3.json
# 首次包默认私有、无法匿名拉取时，使用同一 artifact 的镜像包。
scripts/v3-stack load --manifest /absolute/path/v3.json --bundle /absolute/path/v3-images.tar.gz
```

pull 按 `registry_digest` 固定下载，核对配置 ID后建立清单中的标签；load 先核对包名称、大小和 SHA256。随后两者都执行角色、批次、提交与平台核对。首次发布不自动修改包可见性；离线交付不需要服务器保存 GHCR PAT。env 中的两个镜像引用必须和发布清单完全一致。

## RAM 与 swap 预算

`V3_ACCOUNT_MEMORY` 是每账号 RAM 上限，`V3_ACCOUNT_SWAP` 是额外 swap 上限，默认 `0` 保持禁用。Docker 的内存加 swap 总上限由两者相加生成，账号首次保存预算；历史环境缺 swap 字段时保持关闭。以后修改全局配置不会自动改已有账号预算或身份。

美国服务器起步配置：`V3_ACCOUNT_MEMORY=1536m`、`V3_ACCOUNT_SWAP=2048m`、`V3_MAX_ACTIVE_ACCOUNTS=1`，RAM 1.5 GiB，额外 swap 2 GiB，总额度 3.5 GiB。部署预检分别要求可用 RAM 至少为账号预算加 1 GiB、空闲 swap 足够覆盖活跃账号额度且 Docker 支持 swap 限额；显式更高的 `V3_MIN_FREE_MEMORY_BYTES` 仍生效。默认 4 GiB、单账号配置继续要求至少 5 GiB 可用 RAM，swap 不能代替物理余量。起步上限不代表真实 CLI 的峰值已经验证。

首次使用空目录；不复制旧账号有效 RT。每账号 HOME、CA、工作目录、CLI 版本缓存和 Recorder 证据归属保存在 `bench/environments/<环境 ID>`。停止固定容器保留目录和容器，重启服务先对账遗留执行。停止入口按产品及部署标签收口，不 prune Docker、不删除数据或旧网络。

升级前先 `stop`，再 `backup` 到全新且独立的目录。备份包含持久 HOME、凭据、工作目录、证据、联合镜像清单与 SQLite backup API 快照，目录权限为 0700；运行期间和已有备份目录都拒绝操作。备份含账号秘密，应按当前数据目录的权限保管。

v3 回退先停止当前批次并保留最新停机备份。只在布局/桥协议兼容时，把 env 中两个镜像及清单一起切回已保存的兼容批次，再 check/up；通过“环境与任务”的重建操作替换已停止的旧批次容器，保留环境 ID 和持久 HOME。未完成重建的环境会拒绝发送，不静默混用镜像。数据库或布局不兼容时不能直接回退镜像，需先在独立离线目录核对快照与最新凭据所有者，再安排恢复；没有自动恢复数据库或切回旧版的入口。

登录在真实 CLI/tmux 内完成。CLI 与 Rust API 客户端共用账号容器及代理，但仍是不同客户端；固定容器不保证完整指纹相同或避免封禁。身份没有明确来源时不应猜测。遥测专项继续留在后续任务。

养号支持账号级 5h/7d 已用百分比阈值，两个窗口独立配置 1～100 的整数或关闭，默认关闭。达到任一阈值后拒绝后续养号请求，当前已接受请求收尾后暂停，保留原 run/HOME/工作目录/主会话。未知或到期只允许一次正式请求更新额度，仍未知则等待；许可与请求标记持久化，重启/重复点击不重复放行，不新增自动 usage 查询。普通 CLI 与 API 保持原有门禁。此功能需要同批 control/account 镜像，回滚前先关闭阈值并收口等待工作，保留持久数据。

API 与同账号普通 CLI、养号、抓包独立调度，可以同时运行；CLI 之间串行，养号让位于正式 CLI 工作。API 准备发送器不安装 CLI。普通 CLI 的取消、心跳失联、调度器重启只清理本次进程和 CLI 观察上下文，保留账号容器与 API 长流；清理无法确认时标为 `cli_reconcile`，只禁止下一 CLI。旧无模式记录默认排他。重授权、代理修改、绑定切换、停止及重建仍关闭 API 入场并检查或排空已有请求。两条链路共享账号额度及容器资源，容器或公共网络故障仍可能影响两者。

本地验证使用合成账号和 mock 上游，不能将本地通过等同于真实账号已完成验证。生产部署、旧账号接管、真实验证和发布推送需要单独安排。

run 与续聊的证据入口保持固定，各次执行在 `executions/<source_hash>` 下独立保存统计、额度观察、HTTP 和原生 flow；额度恢复不会覆盖旧证据。run 统计汇总各 run 执行，抓包页面展示各代及续聊索引/文件。历史平铺证据仍可读取；未部署的早期 v3 原型目录链接不自动接管。本地演练覆盖同 run 第二代合成 CLI 在原 HOME/cwd 使用 `--resume`，不代表官方 CLI 或真实额度耗尽链路已验证。

```bash
# 需在已安装 orchestrator requirements 的 Python 环境运行。
python3 deploy/v3/run_local_verification.py --manifest /absolute/path/release.json
python3 deploy/v3/verify_stack.py --manifest /absolute/path/release.json
# 已安装 Chrome/Chromium 时，验证真实页面的统一退出和旧 Cookie 重放拒绝。
python3 deploy/v3/verify_stack.py --manifest /absolute/path/release.json --browser
# 验证实际 Recorder 的本地 HTTPS/SSE、未知一次机会及重启不重复。
python3 deploy/v3/verify_warmup_quota.py --manifest /absolute/path/release.json
# 在统一后台验证合成账号阈值配置、保存重读、明暗主题和 390px。
python3 deploy/v3/verify_stack.py --manifest /absolute/path/release.json --browser --warmup-quota
```

演练创建随机部署标识的内部 Docker 网络，使用空 SQLite、合成凭据、CLI 测试替身及仅在本地处理的 SOCKS/DNS/HTTP。Docker 检查分别验证发送器直调和真实网关入口到账号的 ClientHello，断言合法短 DNS 绑定可用、共享 CLI 租约不阻止网关发送、错误账号绑定拒绝且无重复发送；另保持账号发送器 API 长流并启动 CLI 养号/抓包、发送第二次 API，验证 CLI 取消及调度器重启对账后长流继续且容器不变。Rust 的 `cargo test --lib local_https` 另用临时 CA 和回环 TLS 服务验证完整响应、原始字节/头顺序、非信任证书及错误主机名拒绝、长流取消。额外信任根仅编译进测试，正式镜像不提供跳过证书校验或追加测试 CA 的开关。TLS 测试需要 Python3 和 OpenSSL。结束只删除本次创建的测试资料与资源。

整套启动演练使用另一组随机资源和空数据库，核对统一会话、HTTP/SSE/WS 桥、内部路径拒绝、静态终端资源、退出后旧 Cookie 和终端票据拒绝，以及停机保留数据；另建合成旧哨兵，确认新版启停不会修改其容器或数据库。停机后只导入下述合成离线元数据并验证幂等；不读取真实账号或发送上游请求。浏览器验证使用独立临时配置，仅访问本地部署，不读取用户浏览器资料。

`status` 按本部署标签列出两个管理服务和全部动态账号容器，展示实际镜像 digest、环境代次及 API 活动/等待数、CLI 租约与执行证明。网关不可达时占用标为不可用，不把缺失信息当作空闲；输出不含发送器秘密、管理密码或 AT/RT。

旧资料可使用去凭据 JSON 做离线元数据导入，格式见 `fixtures/offline_metadata.json`。只接受账号名、历史任务标题/题号、运行 ID/状态及来源标识；凭据、代理、profile、提示词正文和工作目录内容均拒收。需先初始化并停止独立 v3 部署，默认演练在事务中验证后回滚，显式 `--apply` 才保存。按来源/类型/历史 ID 幂等，内容改变或账号名碰撞拒绝覆盖；账号统一停用且不绑定 cc2api，历史任务归档，未完成运行记为已停止，不恢复调度。真实旧账号接管仍需单独安排。

```bash
scripts/v3-stack import-offline --env /absolute/path/v3.env --source /absolute/path/metadata.json
scripts/v3-stack import-offline --env /absolute/path/v3.env --source /absolute/path/metadata.json --apply
```
