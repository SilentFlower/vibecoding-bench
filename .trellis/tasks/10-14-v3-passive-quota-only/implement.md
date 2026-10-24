# v3 被动额度采集实施计划

## 实施顺序

1. [x] 完成 Brief 评审，通过 `task.py start` 后进入 `trellis-route(target=implement)`；按 before-dev 读取父仓 backend／frontend／deploy 与子仓 backend 规范、实际类和 DTO。
2. [x] 增加纯本地 statusLine 转换／采集，覆盖真实字段、0%、缺失、过期、去重与身份／会话归属；接入 v3 正式作业及恢复，保存原设置并在全部收口路径恢复。
3. [x] 将 CLI 样本接到现有观察游标与 `_observe()`；保留 API／Recorder 观察和原合并语义，验证来源隔离与跨窗口状态。
4. [x] 删除 v3 启动、收尾、批次、养号、后台 tick 的主动 usage 调用与重试门禁；改为被动阈值判断和已有正式执行的单次恢复认领。
5. [x] 禁止 cc2api v3 后台 usage 轮询，保留旧实例和手动查询；补齐手动永久错误分类，收住认证异常恢复。
6. [x] 更新页面来源、未知与阈值等待提示，清除自动查询重试展示；镜像复制新增采集资源。
7. [ ] 执行定向回归及隔离 Docker／官方 CLI／浏览器验证，记录请求计数、字段归属与原生 TLS 证据；通过 Check-All 后更新规范。

## 预期文件范围

- 父仓：`orchestrator/main.py`、`account_runtime.py`、`quota_protocol.py`（如纯函数需要）、相关额度／运行环境测试，新增本地 CLI 采集脚本／测试，`images/v3/Dockerfile`、必要的 worker 生成配置，`webui/app.js`。
- 子仓：`cc2api/src/main.rs`、`src/service/usage_poller.rs`、必要的手动查询错误处理与相关测试；不修改 TLS／重写／选号策略。
- 规范：backend 的被动额度／账号环境及 cc2api 后台轮询契约，任务记录。
- 不纳入既有 `official-protocol-capture.md` 修改和两个 10-12 未提交任务目录。

## 验证计划

- 定向：orchestrator 的额度纯函数、被动消费、自动执行零主动查询、阈值重置与恢复、手动错误分类、执行清理与旧 runner 兼容测试。
- CLI 采集：本地 stdin 转换和文件写入；隔离官方 2.1.293 的正常响应触发 statusLine，核对权限、旧配置恢复、无额外 HTTP／模型请求，不使用封禁账号。
- 父仓回归：`python3 -m unittest discover -s orchestrator -p 'test_*.py'`；新增脚本单测；`python3 -m unittest discover -s deploy/v3 -p 'test_*.py'`；必要的 sidecar 协议副本一致性测试。
- 子仓：`cargo fmt --check`、被动 usage／后台轮询／手动分类的定向测试；按实际修改运行 `cargo test --locked`。如涉及子仓前端再执行 npm build。
- 静态：受影响 Python 编译、Shell／JavaScript 语法、`git diff --check`。
- 集成：固定 HOME／原生 TLS／正常任务与恢复的隔离 Docker 场景，浏览器验证被动／手动来源和未知提示；按改动范围执行，不重复无关发布演练。

## 评审重点与回退点

- 自动 usage 的调用不能藏在缓存、后台轮询、窗口恢复或错误重试中；以请求计数和调用即失败替身验证。
- 删除查询后不得保留会永久等待的 dirty／缓存过期门禁；未知可启动但不可伪造低位事实，真实拒绝及永久错误仍阻断。
- 单次恢复认领要覆盖普通任务、零 run 批次、养号和重启；用户停止、旧会话、旧身份不能复活工作。
- statusLine 采集的本地权限、设置恢复、同值去重和原生 CLI 数据可用性是主要集成风险；失败时保留原用户设置及原项目数据，不以追加模型探测绕过。
- 最终修改范围、规范更新和交付计划以实际 diff 为准；生产切换和 Git 发布遵循既有独立确认流程。


## 当前实现与已验证证据（2026-10-14）

- 已移除 QuotaGuard 自动 usage、300 秒缓存补查与失败重试；手动入口保留，明确永久错误按原门禁收口。
- CLI 采集接入执行／续聊与游标；实际任务设置片段保留临时 statusLine，退出及重启对账恢复旧配置。窗口恢复许可覆盖已命中阈值和阈值关闭时的共同耗尽；续聊／抓包忽略百分比阈值但共享共同耗尽恢复，复用现有持久表。
- cc2api 按 V3_RUNTIME_URL 禁用 usage poller；非 v3 仍按账号开关查询。
- orchestrator 全量回归 247 项通过，状态栏启动修复后的运行环境定向 37 项通过；部署单测 32 项、账号网络回归 8 项通过；Rust 全量 639 项通过、1 项独立 PostgreSQL 验证跳过；cargo fmt、Python 编译、JavaScript 语法通过。
- `deploy/v3/verify_cli_quota.py`：官方 2.1.293、合成 OAuth、Docker network=none。正常 SSE 后采集 5h=42%／7d=35%，原状态栏输出保持；基线与采集场景均为 2 次相同模型请求、零 usage。
- 真实 Chrome 加载当前 WebUI，合成只读 API：未知／被动／手动／历史查询来源正确，页面加载零额度 POST，点击仅一次，批次等待不显示自动重试。
- 联合镜像、Docker 生命周期及统一后台／浏览器验证均已通过。尚未部署或提交，规范同步与交付仍按工作流进行。
- 新增验证资源：`deploy/v3/verify_cli_quota.py`、`fixtures/official_cli_quota.py`、`fixtures/quota_statusline.py`；`verify_local.py` 增加真实 UID1000 输出权限、driver 配置保留、退出／重启恢复断言。

- 实际 Docker 首轮发现普通任务再次调用 write_default_settings 清除了临时状态栏；已恢复仅在本代采集启用时保留 statusLine 的 driver 生成逻辑，并让单测实际执行默认设置函数及后续 Node 片段。此前“仅登录调用”的判断已通过完整脚本与运行证据纠正。
- 联合镜像最终验证批次 `local-20261014-passive-r4`；首次 r1 的已有 hev 组件下载失败（wget=4），r2/r3 重试成功。r3 使用临时本机构建代理，不进入产品运行配置；转发已停止。r4 复用构建缓存后成功。
- 官方 CLI 验证改为调用镜像内 `/usr/local/bin/v3-cli-quota`，仍通过首次未知、正常响应额度与基线请求计数比较。Chrome 额外覆盖 1280/390px 和明暗主题。

- `run_local_verification.py --manifest /tmp/v3-passive-release-r4.json` 通过：v3 实际启动后的配置保留、UID1000 输出权限、退出／重启状态栏恢复、固定 HOME/session、原生 TLS、API 被动观察、API 长流与 CLI 清理隔离、HTTP CONNECT/SOCKS5 字节保真及两账号隔离。

- `verify_stack.py --manifest /tmp/v3-passive-release-r4.json --browser` 通过：统一登录／退出、HTTP/SSE/WS 桥、旧 Cookie 拒绝、独立部署、停机备份及旧哨兵数据／进程保持。
- 最终账号镜像采集脚本 SHA256 与已验证源码一致，共享 quota_protocol 副本一致。最终冻结源码 SHA256：`ceb8021a3be9da710388b56567412af38a588e659739c3108ecc309c3f42c3e2`。
- 当前完整检查证据已覆盖 R1～R6；业务代码无剩余已知问题。真实可用账号在生产部署后的额度响应与零自动 usage 仍由部署负责人验收；本轮未部署、提交或推送。规范同步属于下一工作流阶段。
