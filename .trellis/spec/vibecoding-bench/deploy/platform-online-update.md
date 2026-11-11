# v3 平台在线更新合同

## 1. 范围与触发

适用于 v3 的签名发行、管理页面 `/updates`、Python/Rust 共同维护门禁、独立宿主执行器和首次接入恢复。修改这些边界时，应同步核对本文与实际测试。日常操作见 [系统更新 SOP](../../../../deploy/v3/SYSTEM-UPDATES.md)；原账号归属和内核生命周期继续由 [账号运行时规范](../backend/account-runtime-v3.md) 定义。

默认每六小时检查受信目录，安装由管理员触发。宿主执行器独立于两个控制服务运行，使用固定策略和 Compose 模板。发行材料只提供受限声明。

## 2. 签名与入口

### 管理 API

浏览器沿网关会话鉴权访问 `/runtime/api/system-updates`，管理桥转到调度器 `/api/system-updates`，再以私有令牌访问 Unix socket。

| 方法与相对路径 | 请求 | 返回 |
| --- | --- | --- |
| `GET /status` | 无 | 安装能力、revision、实际组件来源、环境来源、当前操作、历史 |
| `GET /releases` | 无 | 已验签发行、目录新鲜度、检查状态及兼容结论 |
| `POST /check` | 空对象 | `202`，异步检查身份 |
| `POST /prepare`、`/install`、`/rollback` | 冻结操作 | `202`，原操作状态 |
| `GET /operations/{operation_id}` | 原 UUID | 脱敏进度 |
| `POST /operations/{operation_id}/cancel`、`recover` | `expected_revision` | `202`，原操作状态 |

核心校验签名位于 `orchestrator/system_update_contract.py`：

```python
validate_release(value: dict) -> dict
validate_index(value: dict, highest: list[int] | None = None, now: float | None = None) -> dict
validate_operation(value: dict) -> dict
compatible_data(original: dict, target: dict) -> bool
```

首次接入使用 `python3 deploy/v3/install_system_updater.py prepare --env <配置> --release-dir <发行目录> --state-root <目录> --public-key <公钥>`；提交使用 `finalize --policy <策略>`。两者默认预览，实际执行显式追加 `--apply`。

## 3. 数据与环境合同

### 受信发行

- 独立 Ed25519 密钥由 CI secret `V3_SYSTEM_RELEASE_PRIVATE_KEY` 提供。宿主保存 64 位十六进制公钥，签名原始长度为 64 字节，按原始 JSON 字节验签。
- 平台发行 `system-ci-*` 的必需字段为 `schema_version=1`、`release`、`sequence`、`published_at`、`platform`、`build_manifests`、`control`、`account`、`compatibility`、`data_compatibility`、`changes`、`bundle`。平台固定为 `linux/amd64`。
- 组件字段固定为 `release`、`reference`、`registry_digest`、`config_digest`、`revision`、`unpacked_bytes`、`content_sha256`。镜像仓固定为 `ghcr.io/silentflower/vibebench-v3-{control|account}`，精确来源为 `v3-ci-*`。仓库摘要、配置摘要和内容摘要分别校验。
- 兼容能力固定为 `updater=1`、`gate=1`、`bridge=1`、`layout=2`、`cli_install=2`、`credential_ownership=1`、`account_protocols=[1]`。
- 双库 `bench`、`gateway` 各有 `contract` 和 `rollback_compatible`。目标声明必须包含原版合同，才允许在线切换。默认策略仅认可自身合同。新增旧合同需要实际兼容验证。
- 签名目录字段固定为 `schema_version=1`、`sequence`、`issued_at`、`expires_at`、`releases`。目录和签名从同一 Git commit 获取；序号不得低于最高已接受序号。发布有效期为 30 天，校验上限为 31 天。准备和安装需要新鲜目录；回退使用独立验签的已安装历史。
- 清单上限 128 KiB，目录上限 256 KiB，版本说明上限 8000 字符，持久状态与操作读取上限 8 MiB。重复 JSON 字段、非有限数字和未知字段拒绝。下载采用固定 HTTPS 来源、有限重定向及有界字节数。

### 冻结操作与响应

冻结写请求精确包含以下字段，Pydantic 拒绝附加字段及布尔值冒充整数：

| 字段 | 约束 |
| --- | --- |
| `operation_id` | 规范形式 UUID，本次操作唯一身份 |
| `expected_revision` | 状态接口取得的规范形式 UUID |
| `target_release` | 精确 `system-ci-*` 发行 |
| `target_manifest_sha256` | 原始清单 SHA256，64 位小写十六进制 |
| `drain_timeout_seconds` | 整数 60～7200，API 默认 900 |

同一 UUID 与同一动作、参数重试返回原操作。复用 UUID 改动参数属于冲突。取消与恢复请求精确包含 `expected_revision`。

已接入状态包含 `installed`、`revision`、`deployment`、`current_release`、`components`、`operation`、`busy`、`history`、`checked_at`、`check_error`；管理桥补充 `environments`。未接入返回 `installed=false` 与接入说明。公开操作只包含 `operation_id`、`action`、`phase`、`created_at`、`updated_at`、`target_release`、`error`、`blockers`、`cancel_requested`、`cleanup`、`environment_results`。

### 来源、准入与恢复

- `V3_RELEASE` 表示平台来源；`V3_ACCOUNT_RELEASE` 表示选定账号镜像来源。共享只读门禁通过 `V3_UPDATE_GATE_DIR` 接入；调度器通过 `V3_UPDATE_SOCKET_DIR` 连接更新服务。
- 账号私有 `runtime/account-image.json` 固定 `schema_version`、`environment_id`、`release`、`reference`、`image_id`、`protocol`，与真实 Docker image ID、标签及原角色归属共同核验。首次旧角色通过受控生命周期重建建立来源。
- 仅平台变化且账号内容摘要相同时，保留原账号镜像、三角色容器 ID、环境代次及内核选择。账号内容变化时逐项重建原本运行的环境；原本停止或退休的环境保留状态。
- 门禁 `admission.json` 固定 `schema_version`、`deployment`、`operation_id`、`epoch`、`phase`、`target_release`、`revision`、`created_at`；phase 为 `idle|blocked`。目录 0700、私有文件 0600，拒绝符号链接等不安全读取。接入后缺失或损坏门禁进入拒绝准入和对账路径。
- 两端活动计数覆盖响应正文 EOF、错误及断连。批次排队等待属于待认领工作；有限分派事务和实际执行计入活动。维护期间保留待认领项，释放门禁或控制重启后继续调度。
- 原工程或登录只能凭实际仍登记的有限作业续接。续接继续检查身份、时间窗口与配额；作业撤销后证明失效。
- 排空核对实际 API、jobs、executions、租约、sender、CLI 孤儿、三角色镜像及未决意图。未知活动阻断切换。排空超时和切换前取消按原操作释放门禁。
- 安装正常阶段为 `preparing → draining → switching → verifying → committing → cleaning → succeeded`。单独 prepare 在 `prepared` 完成。恢复按持久意图、真实容器、配置 CAS、软件字段 CAS 与双库/身份摘要确定动作；不确定现场进入 `reconcile`。
- 账号部分恢复最多允许冻结的原版和候选两个实际镜像 ID。恢复仍要求环境、代次、epoch 以及原作业证明一致。恢复已释放的门禁前重新检查后来工作。
- `finalize --apply` 与独立执行器共用 `service.lock` 及存储维护锁。原首次接入在状态提交后、门禁释放前后中断，均可用同一发行重试收口。已完成重试保留原 `installed_at`；外来门禁和后来 revision 拒绝覆盖。
- 清理保护当前组合、最近两个完整历史组合、全部容器引用和恢复引用。只精确删除经证明的历史镜像；Docker 删除最后一个 tag 时可同步移除其 RepoDigest。清理失败记录 `succeeded_cleanup_pending`，通过原操作恢复重试。

## 4. 校验与错误矩阵

| 条件 | 行为 |
| --- | --- |
| DTO 类型或附加字段错误 | 管理 API `422` |
| UUID、摘要、发行、等待范围或材料校验失败 | `400` |
| UUID 参数复用、旧 revision、已有活动操作、现场 CAS 冲突 | `409`，刷新状态再确认 |
| Unix peer UID 或私有令牌错误 | 执行器 `403` |
| 独立服务连接失败 | 管理桥 `503`，状态允许重试 |
| 维护期间新业务请求 | `503` 与 `Retry-After`；迟到原登录证明返回 `409` |
| 签名错误、目录回放/过期、数据合同不兼容 | 准备/安装受阻，记录具体原因 |
| 未知进程、租约或角色归属 | 阻止切换，按实际阶段等待或进入 `reconcile` |
| 首次接入遇到活动服务锁 | 拒绝提交；按 SOP 停止独立更新服务后重试原 finalize |

## 5. 场景与示例

正常：管理员读取 status 与 releases，用页面生成的 UUID、当前 revision 和清单摘要提交 install。下载时继续服务；排空完成后切换控制服务，验收成功持久提交并恢复准入。

边界：长响应仍在发送时，活动计数一直保留到正文结束。批次下一项在维护期间等待，当前有限执行结束后计数归零。控制重启保留原待认领项。目录过期时检查新目录；已安装历史仍按数据兼容条件提供回退。

错误用法：收到 `409` 后仅替换 UUID 自动重放原确认。正确处理：重新读取 revision、候选摘要和重建范围，再由管理员确认新请求。

错误用法：首次 finalize 中断后直接写 idle 门禁。正确处理：重试原 `finalize --policy <原策略> --apply`，由原发行、epoch、配置及共享服务锁证明收口。

错误用法：将整个批次等待循环计入维护活动，或以原作业证明绕过配额。正确处理：只登记有限分派和执行，续接保留其他准入校验。

## 6. 必需验证与断言

- `deploy/v3/test_system_*.py`：签名、目录顺序/时间、严格字段与大小、数据兼容、同参幂等、revision 冲突、恢复与清理保护。首次接入覆盖 dry-run、状态提交中断、释放响应中断、原 installed_at、外来门禁、后来 revision、配置 CAS、真实文件锁互斥。
- `orchestrator/test_system_update*.py`：实际线程/文件准入、ASGI 正文结束、原登录撤销、部分恢复边界；真实 Scheduler + SQLite 验证批次等待不阻塞排空、维护抢先分派、重启续调度、原工程续接与时间窗口/被动配额拒绝。
- Rust `cargo test` 与 `cargo fmt --check`：门禁启动验证、完整 HttpBody 释放、租约与管理桥回归。Vue `npm --prefix web run build` 验证类型和构建。
- `verify_system_update_browser.py`：真实构建页面配合合成 API，覆盖桌面/移动端、确认、断线重连、409、回退/恢复、未接入；断言零脚本异常与零真实模型调用。
- `verify_system_update.py`：随机部署、独立数据根、本地 TLS 和合成密钥下验证真实 Docker 长流排空、控制复用、账号重建、停止状态保留、显式回退、健康失败恢复、部分角色恢复、独立进程中断恢复、容器引用保护与精确回收。Bookworm 二进制沿项目 Docker 构建路径验证兼容性。
- 生产首次接入、CI 私钥配置和真实发行获取由上线单另行核验。进程中断证据命名为进程恢复，宿主重启采用独立现场核验。
