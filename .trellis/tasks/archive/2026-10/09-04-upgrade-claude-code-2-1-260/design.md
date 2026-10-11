# 技术设计

## 设计目标

把 2.1.260 升级拆成四个可独立验收的子任务，并允许 bench 先于 cc2api 发布：

```text
bench 2.1.260 全量升级 + run 版本快照修复 + 生产发布
  -> 用户采集 Opus / Sonnet / Fable 5.1 / Haiku 抓包
  -> cc2api 2.1.260 协议画像适配
  -> cc2api 发布、跨项目一致性与回滚材料保留
```

父任务只维护跨任务契约和最终验收，不直接修改业务代码。

## bench 先行发布边界

- bench worker 模型请求继续直连 Anthropic，cc2api 绑定仅提供账号凭据同步，因此 bench
  发布 2.1.260 不依赖 cc2api 先放开 `allowed_claude_code_versions`。
- bench 不维护隔离环境或双版本默认值；新 worker 的代码、环境和页面默认全部切换到
  2.1.260。
- cc2api 网关仍保持 2.1.257 默认画像，直到真实 2.1.260 抓包完成分析。

## run 版本快照

在 `runs` 表新增 nullable `claude_code_version TEXT`，语义是该 run 首次创建时选定的
Claude Code CLI 版本。

```text
创建 run
  -> 解析一次 effective_claude_code_version()
  -> 与 run 行原子写入 claude_code_version
  -> scheduler / Runner 使用 task 或 run 中的快照
  -> continue 查询 runs.claude_code_version
  -> 继续 worker 复用原版本
```

- 普通、批量、养号和抓包入口均在创建 run 行时保存快照，避免排队期间全局设置变化。
- 同一 task 的“再次运行”会创建新的 run，因此使用再次运行当时的当前版本。
- `Runner.start_run()` 优先使用传入的 run 版本，旧调用或历史记录缺失时才回退当前有效
  版本。
- `Runner.start_continue()` 优先使用 `runs.claude_code_version`；历史 run 字段为空时
  回退当前有效版本。回退值应尽早补写，避免同一历史 run 后续继续再次漂移。
- run 列表、详情和抓包详情沿用现有 `SELECT *` 自动返回字段；抓包创建响应显式返回版本，
  便于用户在开始取证前确认。

## 抓包证据边界

- 用户负责在 bench 发布后产生真实 run ID；证据子任务负责只读拉取、脱敏分析和最小
  fixture。
- 至少覆盖 Opus、Sonnet、Fable 5.1、Haiku；如果实际仍出现 Fable 5，则追加独立
  样本。
- 协议判断以请求类型为单位，不能只按版本统一推断 CCH、beta 或 body 结构。

## cc2api 画像边界

- 在 `version_profile.rs` 新增独立 2.1.260 profile，2.1.257 完整保留为回滚画像。
- `rewriter`、`gateway`、`telemetry`、OAuth、session hello、settings/DB 和 Web 设置页
  只实现抓包已证明的差异。
- 默认值迁移使用“仍等于旧默认组合才升级”的条件迁移，不覆盖管理员自定义设置。

## 发布与回滚

- 2026-09-05 用户确认取消本次完整回滚演练的收尾要求，保留未执行说明和旧镜像/DB
  备份；不追加测试，不修改通用规范。下面的版本协调约束仍用于未来实际故障回滚。
- bench 子任务自己完成三镜像发布和生产部署，记录旧 tag、页面版本覆盖和数据库快照。
- cc2api 发布单独执行，记录旧镜像和 settings/account 版本分布。
- 最终回滚必须保证恢复后的 bench CLI 落在恢复后的 cc2api 允许范围内；回滚页面覆盖、
  `.env` 和镜像，不能只切换容器 tag。

## 风险

- 只在容器启动时读取全局版本会重现 continue 漂移，版本必须在 run 创建时持久化。
- 历史 run 无法可靠反推出原始 CLI 版本，只能明确采用兼容回退，不能伪造历史快照。
- 2.1.260 与 2.1.257 版本接近不代表协议相同；所有 hash 和模型子画像仍需抓包证明。
