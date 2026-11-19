# 多平台账号实现与验证记录

## 已实现的合同

- 平台字段缺省 Claude Code，历史存量使用追加迁移 version 5。新界面显式查询 all，旧调用继续取得 CC 视图。
- 同邮箱跨平台独立保存，同平台唯一；平台创建后固定。AGY 同形体开关按账号保存，默认关闭。
- 既有授权与账号保存接口按平台分派。AGY 重授权绑定原账号及凭据代次；代码投递幂等，错账号拒绝写入。
- AGY 原生管理驱动使用固定 1.5.9、私有 HOME 和完整制品 SHA256；身份及模型观测使用 AT-only 原生进程。唯一 RT 刷新进程产生结果后，按原操作、代次与原凭据提交。
- 手工凭据候选同样先由原生管理适配持久保存。有效AT采用AT-only核验。到期AT以候选代理在同操作内执行受管刷新。回复丢失后按原操作恢复候选。
- 结果未知进入 reconcile；原生当前私有文件保留。恢复、旧回执隔离、重启及普通字段差异保存均有独立验证。
- CC 调度、旧 CLI 绑定、上游刷新、原生预热和遥测使用平台守卫。AGY 模型业务由后续运行环境任务接入。
- 构建新增可选 V3_AGY_AUTH_ASSET，固定宿主包同步依赖。受控回退在当前库存在新平台记录时拒绝旧版 control 镜像。

## 已完成的自动证据

| 层次 | 结果 | 证据 |
| --- | --- | --- |
| Rust 完整测试 | PASSED；955 passed，13 ignored | .trellis/.runtime/agy-account-full-rust-tests.log |
| PostgreSQL 专项 | PASSED；任务专用临时 PG15，历史升级、跨平台同邮箱与凭据代次事务 | .trellis/.runtime/agy-account-postgres-tests.log |
| 部署回归 | PASSED；221 项 | .trellis/.runtime/agy-account-deploy-tests.log |
| 新驱动及内部鉴权 | PASSED；15 项，含真实跨进程文件锁、私有权限、单次码投递、TTL、刷新与 ASGI 脱敏 | .trellis/.runtime/agy-auth-tests.log |
| 网关 HTTP + SQLite | PASSED；合成原生服务，覆盖并发一次刷新、丢回复、重启、错身份及原账号回填 | .trellis/.runtime/agy-account-api-tests.log |
| AGY 实际构建 UI | PASSED；平台筛选、两个独立开关、轮询草稿、迟到原生会话取消、原账号重授权及 390px | .trellis/.runtime/agy-account-platform-ui.log |
| CC 账号页回归 | PASSED；保存、取消、分页、授权、代理及 1440/720/390px | .trellis/.runtime/agy-account-browser-tests.log |
| 前端构建、Rustfmt、数据库定义 | PASSED；数据库登记 bench=1 / gateway=5 | .trellis/.runtime/agy-account-web-build.log |
| 固定原版启动/取消 | PASSED；完整 SHA256、真实 Google PKCE 链接、容器回收、模型提交 0 | .trellis/.runtime/agy-native-smoke-result.log |
| 正式 UI → 网关 HTTP → 固定原版 | PASSED；真实 Google 授权链接，关闭窗口后原生会话 cancelled | .trellis/.runtime/agy-native-ui-smoke.log |

完整编排回归执行 1338 项：1332 通过、5 跳过、1 项错误。错误为 `test_project_iterations.ProjectIterationTests.test_retired_generated_content_is_not_a_production_catalog`，直接读取工作树时触发 python-dateutil 的固定 seed 摘要不符。

按现有 `manage.restore_upstream_checkout_bytes` 在独立交付副本恢复两份已登记原件后，该用例通过（1/1）。证据为 `.trellis/.runtime/agy-account-catalog-staging-test.log`。源码检出行尾与交付副本分别报告，完整工作树原命令的失败保留。既有需要专用原生/回环设施的 ignored 用例分别报告。PostgreSQL 专项已经显式运行。

上述 HTTP 和浏览器的凭据、身份与额度回执为合成材料。固定原版启动证据只覆盖 Google 授权链接生成与取消。

## 真实 OAuth 外部系统上线后验证

- 隔离账号页已准备；运行信息只保存在 .trellis/.runtime/agy-native-acceptance/ready.json。
- 使用本任务独立 SQLite 和固定原版镜像，数据与业务实例隔离。浏览器完成 Google 授权后，在该账号页提交授权码并保存账号。
- 后续从该独立数据根验证真实身份、持久凭据、AT-only 状态、原生目录、单次受管刷新与原账号重授权。
- 真实授权、真实身份读取及真实刷新尚待完成。模型提交预算始终为 0。
- 用户在四项修复重检后明确取消本轮人工验收前置。本轮以工程自动证据收尾；后续运行环境任务或发布执行方在具备授权测试账号后补验真实登录、身份、目录和单次刷新，预期轮换结果和能力同代保存，模型提交为0。

## 后续任务消费

- 运行环境任务消费 platform、AGY 权威凭据状态/代次与 AT-only 发布限制。旧常驻原生 TokenSource 保留缓存的事实继续适用。
- 同形体任务消费 agy_system_prompt_homoglyph_enabled；本任务只保存开关。
- 请求记录任务按平台、账号与代次记录实际采用策略。AGY 的现有管理能力观测保存在 usage_data.capabilities，保留 source 和 observed_at_ms。

## 账号筛选 UI 反馈修正

用户指出平台下拉的表单标签使工具栏错位。原构建的实际控件顶部为 189.48px，状态组顶部为 175.48px，相差 14px。

已将平台筛选改为工具栏局部紧凑布局，保留读屏名称“平台筛选”。平台、状态与搜索沿原控件高度对齐。390px 下平台及搜索位于首行，状态筛选独占下一行。平台选择显式先更新值，再与当前状态、搜索共同查询并重置页码。

`verify_account_filters_ui.py` 已通过 390/720/1440/1920px 实际构建验证，包括等高对齐、无横向溢出、键盘 Escape 与焦点返回、平台/状态/搜索组合查询和迟到响应隔离。截图位于 `.trellis/.runtime/account-filters-<width>.png`。构建日志为 `.trellis/.runtime/agy-toolbar-web-build.log`。

用户明确本轮真实 Google 登录尚未测试。该项保留为未验证。

## Check-All 四项修复复验

四项原问题均已修复并完成重检，问题编号沿用CHK-001、CHK-002、FBK-001、FBK-002。重检画像为requested=auto、effective=full、confidence=high，依据是持久状态机、凭据事务及制品交付身份发生行为变化。

| 验证组 | 当前证据与结论 |
| --- | --- |
| Rust完整回归 | 957通过、13忽略。agy-repair-full-rust-tests.log；最后SQL类型修正另由存储和PG专项覆盖 |
| SQLite存储 | 5通过；覆盖终止归属、迟到提交、能力创建及代理/凭据/能力原子提交与回滚。agy-repair-store-tests.log |
| PostgreSQL专项 | 1通过；独立PG15，历史迁移、TEXT能力/时间列、代理与新代提交。agy-repair-postgres-tests.log |
| 驱动与ASGI | 18通过；缺失操作持久终止、跨重启与迟到RT拦截、新代理刷新后故障恢复。agy-repair-driver-tests.log |
| 部署回归 | 原完整批次223项中222通过、1项子进程等待超时。该项随后单独复测通过（1/1）；原失败记录保留。agy-repair-deploy-tests.log、agy-repair-deploy-timeout-recheck.log |
| 网关HTTP与SQLite | 通过；创建/重授权/重启能力回读、未落盘失败恢复与重新授权、到期AT新代理轮换后回执丢失恢复。agy-repair-api-tests.log |
| AGY浏览器 | 通过；平台、独立开关、草稿、迟到会话取消及原账号授权。agy-repair-agy-ui-tests.log |
| CC浏览器 | 通过；既有账号管理及1440/720/390px。agy-repair-cc-ui-tests.log |
| 格式及定义 | git diff --check、cargo fmt --check及verify_database_definitions.py通过；bench=1/gateway=5 |

上述日志位于.trellis/.runtime/。部署故障项为test_native_probe_lock_covers_preflight_refresh_and_restore，本轮单独复测用时0.334秒。超时根因保留不确定，不将其归为功能修复。制品切换的两项新测试包含在223项内；固定源码下未携带与携带原版双向均触发账号镜像重建，错误声明在签发前拒绝。

PostgreSQL复验发现历史usage_fetched_at为TEXT。新能力写入与CAS使用UTC文本，OAuth专用时间列继续使用其既有TIMESTAMPTZ转换。独立PG复验通过。临时PG容器已回收。

重检三个维度均已对照原需求、设计、实际跨层链路和旧有效证据。四项修复结论通过。真实Google授权、身份和刷新保持未验证。用户最新指示将本轮验收边界调整为工程自动验证，外部系统验收登记为上线后验证。编排工作树全测的既有行尾夹具错误及独立交付副本通过证据沿用上文记录。

本任务隔离验收服务已加载最新网关和驱动，入口http://127.0.0.1:39409/。运行归属保存在agy-native-acceptance/ready.json。模型提交数为0。

## 最终检查收尾

复用四项修复的有效完整检查及定向复验，剩余CHK=0、FBK=0。用户明确取消本轮人工验收前置，真实Google登录不计入已验证证据。编排既有失败项采用已完成的交付副本还原复验闭合，原工作树失败记录保留。当前工程检查通过，继续规范同步及精确提交计划。
