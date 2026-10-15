# 技术设计

## 问题与证据

- `orchestrator/account_runtime.py:1740` 的 `identity_import()` 仅接受 `runtime/identity.json`。
- 唯一生产者是 `images/sidecar/recorder.py:707` 的完整 `/v1/messages` 请求观察；普通 v3 CLI 使用 `passthrough`，不会执行该路径。
- 只读线上检查确认目标环境已运行普通任务，但身份文件不存在。
- 官方 2.1.293 二进制中，请求 metadata 的 device_id 读取持久配置的 userID；machineID 是另一个独立字段。无外网 Docker 实测两条本地模型请求均验证此映射，见 `research/official-cli-identity-result.json`。
- 已绑定重授权的 `LoginManager.commit_bound()` 先导入／查询回执，再调用 `finish_bound_login()` 镜像凭据。Python 18 项与 Rust login_import 4 项现有回归均通过；未发现这条路径只写本地却返回远端成功的证据。

## 边界与契约

### 1. 本地 CLI 身份来源

为当前已验证版本 2.1.293 增加独立、明确的来源标识 `cli:2.1.293:config.userID`。版本支持必须来自官方 CLI 的隔离请求验证，不能因字段名相同就扩展到所有版本。

从固定环境 HOME 读取 `.claude.json.userID` 与 `oauthAccount.accountUuid`，并与管理 profile 的登录账号归属核对。userID 必须为 64 位小写十六进制；缺失、格式异常、账号归属不一致均返回受控错误。不得生成新 ID，不读取 Linux `/etc/machine-id` 或用 `.claude.json.machineID` 替代。

已有 Recorder 实际观察记录继续可用。历史记录损坏、标记冲突、账号不符，或在已验证版本中与当前 userID 不一致时，阻止同步；不能用新来源覆盖旧冲突。其他版本仅在已有明确请求观察证据时沿用旧路径；缺少证据时准确提示版本身份来源未验证。

读取与校验收敛到一个可复用的只读 helper。`identity_import()` 复用其结果并继续采集基础环境；环境列表也复用校验结果展示准确状态，GET 不创建容器、不生成身份文件、不唤醒环境。身份读取需要遵守既有账号／profile／环境锁序，避免在登录、绑定切换或持久配置写入期间接受混合快照。

### 2. cc2api 导入兼容

`CliIdentityImport` 的现有字段保持。`cc2api/src/handler/router.rs` 在原有受信任服务验证下接受两类来源：原有请求观察来源，以及与 canonical_env.version / version_base 精确匹配的 2.1.293 本地配置来源。环境 ID、设备格式、账号 OAuth、Linux 运行环境等已有校验保留；不开放任意 source，也不更新已存在账号的设备身份。

初次同步与已有账号绑定均继续使用同一身份核对链；相同邮箱或 UUID 不能越过设备冲突检查。凭据刷新权仍在 cc2api，绑定 HOME 不持有刷新令牌。

隔离验收补充发现：SQLite 创建账号接口已返回 201 和新 ID，但独立数据库连接尚看不到该记录，紧接的凭据解析返回 404；下一次创建才使前一条记录可见。`AccountStore::create` 的 `INSERT ... RETURNING` 必须完整消费执行结果后才报告成功，保留单行 ID／时间回填及 SQLite／PostgreSQL 兼容，不加盲目重试、不改变 schema。增加独立连接立即读取的回归，再重跑首次同步到重授权的完整链路。

### 3. 重授权结果

已绑定账号继续复用现有提交和回执流程，不重写 OAuth 事务。只有远端提交与本地镜像／收口成功才返回 `credentials_synced:true`；错误登录、丢失响应、未知结果及局部镜像失败保留门禁与可恢复材料。

未绑定 v3 账号保存成功时明确返回 `cc2api_account_id:null` 与 `credentials_synced:false`。页面对 v3 本地重授权提示“已重新授权，仅保存到本地，尚未关联 cc2api”；已绑定成功仍明确提示同步到原关联账号。不根据邮箱自动创建绑定，不将浏览器授权完成等同于提交成功。非 v3 的现有流程保持。

## 影响文件

- `orchestrator/account_runtime.py`：统一身份读取／校验与导出。
- `orchestrator/main.py`：环境身份状态、未绑定 v3 登录提交结果。
- `webui/app.js`：根据真实同步结果展示完成提示。
- `cc2api/src/handler/router.rs`：新增受控身份来源校验及对应测试。
- `cc2api/src/store/account_store.rs` 与现有 store 集成测试：补齐首次创建返回前的持久化完成保证。
- 现有 Python 测试及 v3 隔离验证资源：身份缺失／冲突、已绑定／未绑定重授权、官方 CLI 来源回归。
- 相应 backend／frontend spec：更新身份来源和结果说明。旧的“必须观察完整模型请求”契约须同步修正，不能仅改实现。

## 验证与兼容

1. Python 使用临时 SQLite、HOME、profile 和 Docker／管理 API 替身，验证首次登录无任务也能同步、普通任务后的同一身份、错误和竞争边界。
2. 官方 CLI 2.1.293 使用空合成 HOME，设置不同的 userID 与 machineID，network=none，只请求本地响应服务，验证真实 metadata；重跑时必须仍一致。
3. Rust 验证两类来源、版本不符、任意来源与缺少内部服务凭据的拒绝；继续验证 login_import 的真实 SQLite 凭据与回执。
4. 使用现有 v3 隔离堆栈验证首次同步后重授权：实际 gateway 数据库与管理 profile 的 AT/RT 一致，主 HOME 仅发布 AT，账号 ID／设备／限流状态不变。页面检查两类完成提示。
5. 不读取或输出真实令牌，不向被封账号发送模型或额度请求。

## 交付与回退

本轮范围是本地实现、隔离验证和规范同步。两个仓库与同批 control/account 镜像需要按原联合发布规范交付；本次实现授权不直接切换生产镜像。无新增数据库表和破坏性迁移。旧镜像不认识新身份来源时应失败关闭；回退按兼容同批镜像操作，不修改或删除账号 HOME／凭据／原绑定。
