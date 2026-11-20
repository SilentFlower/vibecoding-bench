# Brief — Native messages 缓存断点 off 与 sub2api

## Goal

- 接通 native 消息缓存断点设置，默认保留原生布局，提供遇到缓存问题时可手动开启的 sub2api 备用策略。

## Scope

- 系统设置、管理接口与 native 请求级缓存策略接通，公开选项收敛为 off／sub2api。
- SQLite／PostgreSQL 存量设置的一次性兼容处理。
- 280／293 worker 能力、恢复握手、缓存选点及已有诊断。
- 设置页说明、相关文档、本地配套候选与跨消费者验证。

## Non-Goals

- auto／rolling／stateful 退出公开选项。
- 软件发布、线上部署和内核激活由独立 SOP 承接。
- 缓存命中及成本收益留待后续真实用量对照。

## Technical Overview

- 设置在每次请求构造时冻结，经 NativeSubmission、sender 和私有请求协议传入 worker，在原生 CCH 封口前应用；保存后对后续请求热生效。
- off 对应 preserve。sub2api 按原有转发清理 messages 断点，再选择末条消息和满足条件的倒数第二条 user 消息尾部；已有 system／tools 断点计入四个总预算，独立 TTL 设置继续生效。
- 首次兼容通过同一数据库事务完成重置与一次性标记，后续管理员保存的模式持久生效。

## Context & Decisions

- 当前 native 已保留调用方或原生 SDK 的缓存布局，缓存可正常工作。本项提供额外改写的控制入口。
- 默认 off；首次接入时，存量 sub2api、auto／rolling／stateful 及 stable／anchored 统一恢复 off。之后可手动开启 sub2api，切回 off 恢复原生布局。
- 显式 sub2api 沿用原有转发的重排语义，共享运行时的合同、测试及文档同步调整。工具业务对象中的同名字段保持原义。
- 依据本任务 prd.md、design.md、implement.md 实施，复用 R1 完成后的热路径。

## Risks

- 一次性重置须覆盖事务失败及并发启动，迁移后手动开启的选择须经重复启动验证。
- 常驻 worker 并发及恢复场景须保持各请求策略归属；旧 worker 在显式 sub2api 能力不足时返回受控 503。
- 原生选点、TTL 与 CCH 的配套变更须使用实际 280／293 执行体及隔离 TLS 验证。

## Acceptance

- 新安装及首次升级均使用 off；随后手动启用 sub2api 并重启，选择持续保留。
- off 保留缓存布局；sub2api 的清理、选点、预算与 TTL 组合符合约定，诊断反映实际处理结果。
- 设置页、GET／PUT 与运行期模式一致；保存后续请求采用新模式，已冻结请求沿原模式执行。
- 双库首次重置、重复执行、并发启动及失败重试通过；无关设置保持原值。
- 280／293、恢复握手、同一暖 worker 切换及隔离 TLS 实收验证通过。

## Next Step

- 启动本子任务，按 trellis-route 进入实现并核对设置迁移及 native 协议定义。
