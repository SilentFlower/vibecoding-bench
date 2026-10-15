# 实施计划

## 顺序

- [x] 1. 用户评审完整 Brief 后启动任务，进入 trellis-route，并按执行模式加载上下文。
- [x] 2. 更新身份来源契约；在 AccountRuntime 增加只读身份读取／校验，接入同步导出和环境列表，保留旧观察与冲突保护。
- [x] 3. cc2api 接受精确匹配版本的新来源并补充路由／服务拒绝用例。
- [x] 4. 为未绑定 v3 的登录提交返回明确的同步状态，调整页面完成提示；保留已绑定的凭据事务与回执恢复逻辑。
- [x] 5. 扩展身份、首次同步、绑定重授权和未绑定重授权回归；将本次官方 CLI 实证纳入可重复隔离验证。
- [x] 5a. 修复隔离验收确认的 SQLite 首次创建可见性缺陷：独立连接测试修改前读取到 0 行而失败；完整消费 RETURNING 后 store 14 项回归通过；新联合批次 r2 构建及全链路验收通过。
- [x] 6. 验证实际 v3 页面／API／本地数据库的一致性，再运行 Check-All、同步规范。
- [x] 7. 展示本次代码和独立交付范围；提交、推送、生产部署只按后续明确授权进行，保留原有 Flower 与其它任务改动。

## 已完成的规划期验证

- Python：`/tmp/vibebench-passive-quota-venv/bin/python -m unittest discover -s orchestrator -p test_login_reauth.py`，18 项通过。
- Rust：`cd cc2api && cargo test --locked --lib login_import_`，4 项通过；存在原有 vendor 编译警告。
- 官方 CLI：2.1.293，二进制 SHA256 为 8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978。无外网 Docker 中两条本地模型请求 device_id 均等于合成 userID，与不同的 machineID 不等；账号归属匹配。
- 上述是现有行为和方案依据的验证，不代表同步缺陷已修复。

## 实施后的验证

- `/tmp/vibebench-passive-quota-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'`
- `cd cc2api && cargo fmt --check && cargo test --locked`，日志写入本地受限临时目录，报告实际通过及跳过项。
- `node --check webui/app.js`
- 官方 CLI 身份隔离验证：已验证版本、重复运行、userID／machineID 明确区分、零外网；只保存字段一致性与数量摘要。
- 本地联合镜像和既有 `deploy/v3/verify_stack.py` / `verify_reauth_stack.py` 流程：扩展首次同步，然后验证真实网关 SQLite、profile 与 HOME 的凭据一致性；界面验证已绑定与未绑定提示。
- `git diff --check`，并对比任务创建时的两个仓库基线，确认本次范围外内容未改。

## 复核要点

- 官方 CLI 版本未验证时不得猜测映射；新来源与版本、账号和环境必须相符。
- GET 不启动或创建环境；同步期间锁序不变，长 IO 不占数据库写锁。
- identity.json 冲突或损坏不能被新来源静默绕过。
- 已绑定重授权只更新原账号，HOME 没有 RT；人工停用、限流与账号政策状态不被不相关操作清除。
- 未绑定本地保存不能显示远端凭据更新成功。

## 当前验证记录

- Python 全量 257 项通过，日志 `/tmp/v3-account-sync-python-tests-final.log`；首次全量中的原有 worker rate_limit 样例失败，单独复测与完整重跑均未复现，未推断具体原因。
- Rust 全量 642 项通过，日志 `/tmp/v3-account-sync-rust-tests-final.log`；原有 PostgreSQL 专项 1 项因未配置临时 DSN 而忽略。新增 WAL 独立连接回归修改前失败、修改后通过，最终定向日志 `/tmp/v3-account-sync-store-final.log`。
- `cargo fmt --check`、`node --check webui/app.js`、变更 Python AST 和两仓 `git diff --check` 通过。
- 实际官方 CLI 2.1.293 禁网验证通过：持久 userID／账号 UUID 匹配真实请求，与 machineID 区分；两模式各 2 条相同本地请求，零 usage，日志 `/tmp/v3-account-sync-official-cli.log`。
- canonical 联合批次 `local-20261015-account-sync-r2` 构建通过，清单 `/tmp/v3-account-sync-r2.json`；按同一 copytree/hash 算法回算当前输入，与冻结源码哈希 `763745212dd9dc6276a58af33546f5a010a57350ee4b54e40fceb53cbd7631df` 一致。
- r2 的 Chrome／HTTP／WS／tmux／SQLite 联合验收通过，日志 `/tmp/v3-account-sync-stack-r2.log`：无任务、无 Recorder 身份文件的首次同步创建并绑定；重授权后原 ID、设备、策略及两端凭据一致，HOME 仅 AT；未绑定保存提示准确；错误身份、取消、丢回包、断线、重启和草稿清理回归通过；旧哨兵 StartedAt／数据库哈希不变。
- 本机 Docker 默认网段池已满；通过 `/tmp/v3-account-sync-isolated-stack.py` 为本次随机部署仅覆盖 Compose IPAM 为不重叠的 `10.231.217.0/24`，所有产品 API、镜像、断言与清理逻辑保持。最终演练无诊断插桩，未清理既有网络。
- 已核对原有 55 条基线变更：tracked diff、untracked 内容与索引摘要均保持。两仓业务修复已按用户确认提交并推送，生产尚未部署。
- 尚未执行真实 OAuth／生产账号凭据更新；发布后使用可用账号验证，需按交付授权处理。原生右键系统粘贴菜单未自动驱动，已用真实键盘 Ctrl+V 验证粘贴。

## 回退点

- 新身份来源、Python 导出与 Rust 校验必须同批交付；任何一侧验证失败停止交付，保持生产环境不变。
- 修复不迁移数据库、不重算设备、不改代理。部分验证失败保留证据并回到相应步骤，不使用真实受限账号探测。
