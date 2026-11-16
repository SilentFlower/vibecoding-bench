# 实施与验证计划

## 开工前

- [x] 完成 Brief 派生、展示及所属确认门。
- [x] `task.py start` 后进入 `trellis-route(target=implement)`，按 inline 路由使用 `trellis-before-dev` 加载上下文；当前任务不要求派生代理。
- [x] 对新增实现入口重新核对真实类型与方法签名，保持现有脏工作区变更归属。

## 实施顺序

1. 增加纯迁移、登记与来源映射；完成 SQLite/PostgreSQL 增量结构及兼容查询。
2. 增加会话匿名键、有效轮次、原子登记、拦截计数、解除及分页存储，明确并发与过期语义。
3. 增加配置默认值、设置校验/保存/热加载；同步 SettingsMap 字符串合同。
4. 将统一封禁入口接入原始消息、count_tokens 及各真实提交/重试边界，覆盖 native293 和 Rust 后端。
5. 在有界 JSON/SSE 响应观察器中识别策略拒答，执行独立封禁写入，保持正常协议字节和既有用量统计。
6. 增加管理员列表/解除 API、TypeScript 类型与统一 api 客户端方法。
7. 增加“会话封禁”页、导航、状态筛选/搜索/分页、解除确认和设置段，复用现有控件。
8. 更新用户配置说明与任务验收证据；质量验证后按 Check-All → Spec → Push 的任务流程推进。

## 必要测试

- 存储：同键并发拒答只创建一个有效轮次；不同令牌/SID 隔离；自然到期、手动解除、重复解除、新轮次、分页排序与拦截计数。
- 配置：默认 1440 分钟、合法保存与热刷新、非法值及溢出拒绝、修改仅影响新轮次、关闭/重新开启。
- 识别：完整截图文案、结构化 reasoning_extraction、策略错误码、refusal stop；普通文本引用、认证失败、429、参数错误等保持独立。
- 网关：第一次真实拒答后第二次“继续”的上游计数不变；count_tokens 同域本地拦截；不同真实会话共用上游 session 仍隔离；查询失败 503。
- 流：分块 SSE、压缩 SSE、HTTP 200 error、native293/Rust、日志 info/关闭诊断；正常输出字节和缓存/遥测合同回归。
- 排队：封禁发生前已入队的请求在提交前复查，禁止因换账号或修复重试绕开封禁。
- 管理：API 鉴权、参数校验、安全摘要、解除幂等与历史保留；UI 空态、错误、分页、剩余时间和 390px。
- 迁移：旧版本 3 数据库升级、空库、幂等、checksum、定义来源、旧程序兼容读取；PostgreSQL SQL 合同核查。

## 验证命令

```bash
cd services/gateway
cargo fmt --check
cargo test --locked
```

```bash
npm --prefix apps/web run build
python3 deploy/flower2api/verify_database_definitions.py
python3 -m unittest discover -s deploy/flower2api -p 'test_database_definitions.py'
```

实现后根据新增用例补充聚焦命令与现有管理UI验证器的适用场景，不使用真实账号制造拒答。

## 风险文件与回退点

- `gateway.rs`：两个后端与多个提交边界；先证明封禁身份独立于映射与诊断。
- `usage.rs`：有界解码观察与正常字节透传；保留现有 SSE/压缩回归。
- `database_migrations.rs` 与迁移登记、`system_release.py`：保持已发布步骤冻结，仅新增迁移。
- 设置开关关闭后停止运行时拦截，保留历史表及兼容新增结构；代码回退依项目原数据库兼容流程。

## 当前验证证据

- 前端：`npm --prefix apps/web run build`，实际产物通过 TypeScript 与 Vite 构建。
- 页面：`.venv/bin/python deploy/flower2api/verify_session_policy_blocks_ui.py`，1440px 和 390px 均通过状态筛选、分页、搜索空态、解除取消/失败重试、设置直达/保存及服务器时间基准检查；证据位于 `.deploy/session-policy-block-ui/`。
- 迁移与发行：`PYTHONPATH=deploy/flower2api .venv/bin/python -m unittest test_database_definitions test_system_release test_system_migrations`，24 项通过。
- Rust：`cargo test --manifest-path services/gateway/Cargo.toml --locked`，最终完整回归 919 项通过、0 项失败、9 项按项目环境条件跳过；请求作用域的并发画像回归在默认测试栈下通过。
- 格式与差异：`cargo fmt --manifest-path services/gateway/Cargo.toml --check`、`git diff --check` 通过。
- CHK-001：`session_policy_block_v3_send_wait_has_no_attempt` 在修复前复现多记 attempt；将封禁复查移至诊断 commit 前后，断言上游调用与诊断 attempt 均为零、拦截次数为一、许可全部释放。最终完整回归包含该用例并通过。
- CHK-002：设计分页时钟字段已同步为 `observed_at_ms`，入口注释已明确只冻结原始会话身份；时长仍在实际拒答识别时读取。
