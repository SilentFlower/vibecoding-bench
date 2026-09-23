# 升级 cc2api 与 vibecoding-bench 到 Claude Code 2.1.260

## Goal

以 Claude Code 2.1.260 的真实运行与抓包证据为基准，分阶段将
`vibecoding-bench` 的 worker 运行时和 `cc2api` 的默认协议画像从 2.1.257
升级到 2.1.260，确保抓包环境、请求拟态、账号迁移、版本访问策略和生产部署使用同一
版本契约，并保留 2.1.257 旧镜像、数据库备份与版本协调记录。

## 本次收尾决定

- 2026-09-05 用户确认本次不做完整联合回滚演练，保留“未执行完整演练”的事实，取消
  该项收尾阻塞；部署子任务原 `CHK-001` 按范围调整关闭，不记作补测通过。
- 使用既有部署、迁移、协议与用户实际使用证据收尾，不追加模型请求、生产 continue
  或回滚副本演练。通用部署规范不变，将来实际回滚仍须独立核验前提。
- 当前仅同步记录，尚未提交归档部署子任务或完成父任务结果汇总。

## Confirmed Facts（规划时基线）

- npm registry 已发布 `@anthropic-ai/claude-code@2.1.260`，发布时间为
  2026-09-03。
- 当前 `vibecoding-bench` 的 worker Dockerfile、entrypoint、orchestrator、Compose、
  WebUI、示例配置和测试默认值均为 2.1.257。
- 当前 `cc2api` 默认画像和允许范围为 2.1.257 / `2.1.89-2.1.257`，并保留
  2.1.220 等历史回滚画像。
- `cc2api` 的版本画像不仅包含版本号，还覆盖 User-Agent、Stainless、Bun、
  `cc_version`、CCH、beta 顺序、模型子画像、bootstrap、telemetry、DB/settings
  迁移和设置页回显；规范要求使用真实抓包验证，不允许只替换常量。
- 2.1.257 升级已证明同一 CLI 版本内不同模型和请求类型可能具有不同 CCH 输入、
  beta、fallback、thinking、body 字段顺序和辅助请求形态。
- 当前 bench 可通过单次完整 HTTP 抓包 run 保存隔离证据，原始抓包位于
  `data/flows/<account>/<topic_id>/<run_id>/`，不得提交敏感原文。
- bench worker 的模型请求仍直连 Anthropic；绑定 cc2api 只用于凭据同步，因此 bench
  可以先全量升级到 2.1.260 并独立发布，cc2api 网关继续保持 2.1.257 画像直至抓包
  适配完成。
- 当前 `runs` 表没有 Claude Code 版本字段；`Runner.start_run()` 和
  `Runner.start_continue()` 分别在启动时重新读取全局 `effective_claude_code_version()`。
  因此一个以 2.1.260 创建的抓包 run，在全局设置恢复 2.1.257 后继续对话，会错误地
  使用 2.1.257 恢复原会话。

## Requirements

### 1. 总任务与阶段边界

- 总任务只维护跨项目目标、阶段依赖、证据门槛和最终集成验收；可独立验收的实现与
  发布工作拆成子任务。
- 执行顺序固定为：bench 全量运行时升级、版本快照修复与独立发布 -> 用户使用生产
  bench 完成 2.1.260 真实抓包 -> cc2api 协议画像适配 -> cc2api 发布与跨项目验收。
- cc2api 协议实现不得早于目标抓包证据；抓包前只允许做不依赖 wire 推断的代码审计和
  验证工具准备。

### 2. vibecoding-bench 运行时升级

- 将 worker Dockerfile、entrypoint、orchestrator fallback、普通/capture/login/
  quota worker 版本传递、两份 Compose、`.env.example`、WebUI、README 和相关测试
  的默认 Claude Code 版本同步到 2.1.260。
- 保持 WebUI SQLite 覆盖值 > 环境默认 > 代码默认的现有优先级，不改变模型、
  effort、代理、OAuth 所有权或抓包隔离规则。
- worker 启动时继续校验实际 `claude --version`；不一致时安装指定版本，安装失败必须
  让 worker 失败，不能静默回退。
- 为抓包阶段提供能够确认实际运行版本、目标模型、run ID 和抓包完整性的可验证入口。
- bench 第一阶段不维护隔离双版本；代码默认值、WebUI 运行时覆盖和生产默认 worker
  全部切到 2.1.260。
- `runs` 必须保存每个 run 创建时选定的 `claude_code_version` 快照。普通、批量、养号
  和抓包入口都写入该字段；同一 task 重新创建的新 run 使用当时的新全局版本。
- 初始 worker 与后续继续对话必须使用同一 run 的版本快照，不受全局版本设置后来修改、
  清空或服务重启影响。
- 旧数据库通过幂等补列升级；历史 run 没有版本快照时允许回退当前有效版本，并在可行
  路径补写快照，保证后续继续稳定。
- run/capture API 应返回实际版本快照，便于抓包前后核验，不依赖人工推断容器环境。

### 3. 2.1.260 抓包证据

- 抓包必须来自实际运行的 Claude Code 2.1.260，并记录 CLI 版本、目标模型、单轮或
  多轮场景、成功/失败终态和 run ID。
- 抓包矩阵至少覆盖当前 cc2api 明确区分的主模型或请求族：Opus、Fable 5.1、Haiku，
  并补充 bench 当前可选的 Sonnet；如 2.1.260 仍实际产生 Fable 5，则额外保留该
  独立画像样本。
- 对容易在后续轮次变化的模型至少保留一份多轮会话；辅助请求、bootstrap、hello、
  telemetry 和 `/v1/messages` 必须在证据摘要中分开统计。
- 证据分析必须核对 identity、User-Agent、Stainless、Bun、build time、
  `cc_version`、CCH、beta 顺序、请求体顶层字段顺序、fallback、thinking、
  bootstrap、telemetry 和新增 endpoint/辅助请求。
- 原始 `.flow`、完整 `http_capture.jsonl`、Authorization、Cookie、Token、邮箱、
  完整 prompt 和响应正文仅保留在本地或远端受控目录；Git 中只记录脱敏统计、最小
  fixture 和可复算结论。

### 4. cc2api 协议画像升级

- 基于抓包新增独立 2.1.260 画像，不能默认复用 2.1.257 的 CCH、beta、fallback、
  thinking、Haiku 分类或 bootstrap 规则。
- 默认 profile、allowed range、账号 canonical env、OAuth/telemetry/session hello
  等画像消费者必须一致切换到 2.1.260，同时完整保留 2.1.257 回滚画像。
- `cc_version` 与 CCH 必须用各模型和请求类型的脱敏抓包样本复算；如果旧算法或 seed
  命中，应以测试证明，而不是因版本接近直接继承。
- 模型识别继续使用精确 ID 决定 wire 画像；仅在明确共享的配额和展示语义中使用
  family 归类，不能把未来相似模型未经验证地并入旧行为。
- DB/settings 迁移必须只升级仍处于 2.1.257 历史默认组合的值；管理员自定义 allowed
  range、system-role 列表、1M allowlist 和其他账号能力设置必须保留。
- 如抓包发现 2.1.260 新增或改变后台辅助请求、endpoint 或超时行为，须单独建模、测试
  或拆成独立子任务，不能在通用 rewriter 中用宽泛条件兜底。

### 5. 发布、兼容与回滚

- bench 子任务通过 Check-All 后先独立构建、发布并部署 2.1.260，作为用户抓包环境；
  cc2api 仍保持 2.1.257，直到抓包与协议适配子任务完成。
- cc2api 实现子任务必须通过 Check-All 并推送可构建提交，之后才能进入 cc2api 发布
  与跨项目验收任务。
- 发布前记录两个系统的旧镜像、数据库/settings 快照和页面版本覆盖值；发布后核验
  容器、HTTP、镜像摘要、worker 实际版本、cc2api 账号版本分布和最近错误日志。
- 联合回滚时，bench 的 CLI 版本必须落在回滚后 cc2api 的允许范围内；WebUI 保存值和
  `.env` 默认值必须一起核对，不能只回滚镜像。

## Draft Task Breakdown

1. `vibecoding-bench-claude-code-2-1-260-runtime`
   - 升级 bench 全部运行时默认值，修复 run 版本快照与继续对话版本漂移，完成 bench
     镜像发布和生产部署。
2. `claude-code-2-1-260-capture-evidence`
   - 接收并分析用户提供的各模型 run，形成脱敏协议差异和可复算 fixture。
3. `cc2api-claude-code-2-1-260-protocol`
   - 基于抓包完成 2.1.260 画像、模型子画像、迁移、前端回显和回归测试。
4. `deploy-cc2api-claude-code-2-1-260`
   - 在抓包和 cc2api 适配通过后发布 cc2api，完成版本一致性核对、回滚材料保留与未演练说明。

子任务名称和边界会在本 PRD 收敛后创建；父任务本身不直接承载业务代码修改。

## Acceptance Criteria

- [ ] bench 的所有新 worker 创建路径在目标抓包环境中实际运行 Claude Code 2.1.260，
      页面覆盖、清空回退、版本格式校验和安装失败行为不回归。
- [ ] 每个新 run 都持久化实际 Claude Code 版本；初始运行与任意次数继续对话始终使用
      同一快照。全局版本从 2.1.260 改回 2.1.257 后，已有 2.1.260 抓包 run 继续时仍
      使用 2.1.260；新 run 使用新的当前版本。
- [ ] 约定抓包矩阵均有可定位 run ID 和脱敏分析结论，关键 `cc_version` / CCH 样本可
      离线复算，原始敏感抓包未进入 Git。
- [ ] cc2api 默认画像、allowed range、账号 canonical env、全部相关 UA 和设置页均为
      2.1.260，2.1.257 回滚画像保持可用。
- [ ] 各已确认模型与请求类型的 beta、body、fallback、thinking、bootstrap、
      telemetry、`cc_version` 和 CCH 与 2.1.260 抓包一致，旧画像测试不回归。
- [ ] cc2api 通过 `cargo fmt --check`、`cargo test`、`cargo test cch` 和 Web 构建；
      bench 通过相关 Python 测试、Compose 校验和当前默认值审计。
- [ ] 联合发布后 HTTP 健康检查、镜像摘要、worker 版本、DB 版本分布和近期日志均通过，
      管理员自定义设置与账号能力开关未被覆盖。
- [ ] 子任务均按各自确认范围完成独立验收，父任务完成版本一致性与回滚材料记录复核；
      本次不要求完整联合回滚演练，不将未演练描述为通过。

## Out of Scope

- 不在抓包证据出现前猜测或实现 2.1.260 的 CCH、beta、模型子画像和新增协议行为。
- 不提交原始抓包、生产凭据或完整会话内容。
- 不在规划阶段构建镜像、修改生产设置、推送代码或重启远程服务。
- 不顺带改变默认模型、1M 策略、配额、代理、OAuth 刷新所有权或其他无抓包证据支持的
  产品行为。
