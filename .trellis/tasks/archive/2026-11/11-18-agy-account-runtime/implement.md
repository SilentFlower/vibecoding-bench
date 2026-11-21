# AGY运行环境与Gemini API实施计划

## 开工前提

- [x] 核对父任务R03/R04/R06、已完成凭据与账号任务、现有实体和路由。
- [x] 只读核对私有研究原型，保存源码身份及正式交付差异。
- [x] 用户确定temperature/topP兼容接收并忽略，沿原生默认执行。
- [x] 明确工程/养号、新Anthropic入口、new-api修改及新模型费用的边界。
- [x] 三件套收敛、完整Brief人工评审通过，task.py start与inline实施路由已经完成。

## 实施顺序

1. 固化原型源码/资源来源，离线核对模型映射、Gemini字段/响应、工具状态机和观察器；建立正式OAuth启动适配及协议测试，验证零模型就绪。技术未知先用静态解析及回环上游解决，不缩减已确定的模型/工具行为。
2. 实现独立AGY契约及现有account-sender的受鉴权准备、状态、执行和取消分支。封存映像共享、私有HOME及AT-only快照各自核验。
3. 在AccountService现有锁内生成带代次AT快照，接入新worker准入、旧在途保留、一次认证恢复和持久状态异常隔离。
4. 接入Gemini路由、API令牌与账号权限、平台选择和现有并发/RPM/维护链路。实现流式响应和非流式聚合，temperature/topP兼容策略有独立断言。
5. 接入原工具轮保留、跨HTTP结果回填、调用方隔离、concurrency=1接续、旧工具收尾后新代下一轮，以及取消/重启/截止处理。
6. 将AGY环境接到现有AccountRuntime、环境列表/维护/资源控件。以离线实测冻结资源分项；必要持久化只追加登记迁移，CC保持回归。
7. 同步镜像staging、分发与执行体身份、组件内容身份和升级兼容。补齐前端类型、环境UI、只读观测和迟到回执隔离。
8. 跑跨层回归、交付事件合同与外部验收记录。按工作流执行Check-All、Spec评估及精确提交计划。

## 预计影响范围

- gateway：handler/router、middleware/auth、model/account/api_token、AccountService、runtime_transport、account-sender及新增Gemini/AGY契约和执行模块；CC专属native_contract与native_runtime仅在必须的分派边界调整。
- orchestrator：AccountRuntime、main.py的现有环境/传输入口、resource_budget/account_isolation及新增agy_runtime包；与账号凭据适配共享已认证模型信息。
- 部署：images/v3/Dockerfile、manage.py及源快照、固定包、组件身份、升级兼容与迁移演练入口。
- web：现有环境页、API类型及对应浏览器验证夹具；统一请求记录页面由后续子任务交付。
- 迁移：若需新增AGY环境归属/元数据，在独立定义中追加新版本、registry和恢复演练；冻结基线保持原摘要。

## 验证矩阵

| 范围 | 关键断言 |
| --- | --- |
| 公共路由 | Gemini模型、生成和SSE；无令牌、禁用令牌、白黑名单、混合key、密钥脱敏及旧CC路径 |
| 输入/响应 | 文本、系统、函数、签名、usage、原始帧、空/安全/失败终态、非流式聚合；temperature/topP缺省/显式均按原生默认 |
| 内部信封 | 账号/平台/环境/部署/凭据代次、版本、秘密、deadline及错误身份拒绝 |
| 原生执行 | OAuth AT-only、完整SHA/封存/FD、就绪PID与CSRF、镜像池复用、背压、真实模型入口计数、零模型准备 |
| 凭据换代 | 唯一RT所有者、新代worker、旧在途保留、并发认证失败一次恢复、已发SSE禁重放 |
| 工具 | 原worker真实回填、同名歧义、错token/账号/调用、重复、concurrency=1、跨到期、取消与失效终态 |
| 生命周期 | 冷启动、资源不足、只读查询、重启、空闲升级、停止排空、遥测和强制回收分别记录 |
| UI | 390/720/1440px、草稿/焦点、轮询、平台能力、迟到回包及CC环境回归 |
| 部署/数据 | 可复现制品、组件启停、旧镜像门禁、原身份/凭据保持、追加迁移和SQLite/PG恢复 |

## 验证命令与证据

既有命令按模块执行，证据保存至gitignored .trellis/.runtime，避免重复运行内容仍有效的完整验证。

```bash
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s services/orchestrator
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s deploy/flower2api
python3 deploy/flower2api/verify_database_definitions.py
npm --prefix apps/web run build
```

实现时新增AGY原生/回环、Gemini HTTP/SQLite及环境浏览器验证入口，覆盖上表断言。隔离原生探针仅使用明确任务镜像、合成秘密、回环服务及固定执行体，真实Google生成预算0。若实际修改services/runtime的TS代码，再执行该模块bun类型、单元及集成检查。原生、合成和外部未验证项分别报告。

## 回退、交接与收尾

已落地专用入口：verify_agy_runtime.py（固定原版、断网、两代准备及异常收口）、verify_agy_gemini.py（真实Rust HTTP/SQLite，私有发送边界替身）、verify_agy_native_loopback.py（真实网关/发送器/固定原版/TLS/MCP业务闭环）、verify_agy_environment_ui.py（真实Vue及合成后台）。具体命令、结果与已有项目内容基线异常见research/implementation-validation.md。test_agy_runtime直接连接真实Kernel和Broker类，核验工具回填方法及重复拒绝。

- 产品字段、输入/事件协议及迁移写入前先核对真实定义和消费者。
- 外部原型只作冻结输入参考；正式镜像和源码测试不得依赖开发机私有路径、测试API Key或测试CA。
- 新配置失败保持原实例/权威凭据并标记对账；停止/回退仅处理明确归属的实例，未知在途不自动重放。
- 将事件、模型、代次、工具、参数兼容及资源口径交给同形体和请求记录子任务，外部真实验收由后续授权条件承接。
