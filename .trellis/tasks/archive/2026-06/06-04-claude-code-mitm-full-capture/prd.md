# Claude Code MITM 完整抓包分析模式

## Goal

在现有 vibecoding-bench 的账号、topic、worker、sidecar MITM 链路上，新增一个独立的“完整抓包分析模式”。用户可以选择一个 topic 和一个账号，启动一次专门用于 Claude Code 版本差异分析的 run，完整捕获 Anthropic / Claude Code 相关 HTTP 请求与响应内容，并提取遥测、`x-anthropic-billing-header` / `cc_version`、CCH/请求指纹等关键字段，形成可供后续升级 `/root/project/cc2api` 使用的离线分析资产。

## Background / Known Context

- README 已说明项目通过 sidecar 容器、hev-socks5-tunnel、mitmproxy 11 做透明代理和 TLS MITM。
- `images/sidecar/recorder.py` 当前只写 `stats.jsonl` 摘要，字段包括 request/response phase、host、method、path、status、bytes、usage。
- `images/sidecar/start.sh` 已支持 `SAVE_FULL_FLOWS=1` 时用 `--save-stream-file` 保存 mitmproxy `.flow`。
- `orchestrator/main.py` 的普通 run 会创建 `data/flows/<account>/<task_id>/<run_id>/`，并把该目录挂载为 sidecar 的 `/flows`。
- `runs` 表已有 `flows_dir` 字段，run 详情已有 transcript、workspace 文件、token stats 接口。
- WebUI 当前有 accounts、topics、tasks、runs 四个 tab；批次任务支持选择账号和多个 topic，运行详情会展示 token、文件树和 transcript。
- 用户目标是分析 Claude Code 版本之间的请求差异，后续服务于 `/root/project/cc2api` 的版本升级；本任务不直接修改 `cc2api`。

## Requirements

- 新增一个面向单次分析的入口，用户可以选择一个账号和一个 topic，启动完整抓包 run。
- 分析 run 必须复用现有账号 profile、SOCKS5 上游代理、环境指纹派生、worker 执行、sidecar MITM、run 状态流转和停止能力。
- 分析 run 必须强制完整捕获目标流量，不依赖全局 `SAVE_FULL_FLOWS` 默认值。
- 捕获范围必须覆盖 Anthropic / Claude Code 相关流量，包括但不限于：
  - `anthropic.com`、`claude.com` 域名相关请求；
  - `/v1/`、`/api/oauth/`、`/api/eval/`、`/api/claude_code/` 等 Claude Code 常见 API 路径；
  - 遥测、策略、额度、消息、SSE 等请求和响应。
- 每条捕获记录必须尽量保存：
  - 时间戳、flow id、host、method、path、query、status、content-type；
  - 请求 headers、请求体全文；
  - 响应 headers、响应体全文；
  - body 编码/截断/解析状态；
  - usage 信息（如果响应可提取）；
  - `x-anthropic-billing-header` 原文及解析出的 `cc_version` / `cc_entrypoint`；
  - CCH/请求指纹相关 header 或字段（如果请求里存在）。
- 捕获文件必须放在该 run 的 flows 目录下，便于从 run id 反查。
- UI 必须能看到分析 run 和普通 run 的区别，并能在 run 详情里发现完整抓包产物。
- 后端必须提供至少一个稳定接口，用于列出或下载分析抓包产物。
- 默认不得把 OAuth access token、refresh token、cookie 等凭据明文暴露在 WebUI 预览里。
- 文件落盘可以保存完整原文用于本地离线分析，但 UI 预览和索引必须做敏感字段脱敏。
- 默认保存请求体全文和响应体全文，不做 body 大小截断；这只适用于分析抓包模式，不影响普通 run。
- 文档必须说明抓包输出目录、文件结构、敏感数据风险、如何用这些资产做版本差异分析。

## Acceptance Criteria

- [ ] WebUI 存在可用入口，可以选择 `topic + account` 并启动一条分析 run。
- [ ] 分析 run 完成后，`data/flows/<account>/<task_id>/<run_id>/` 下存在完整捕获文件和结构化索引文件。
- [ ] 结构化索引能列出每条目标请求的 method、host、path、status、请求/响应大小、关键指纹字段。
- [ ] 至少一个实际 Claude Code run 能捕获到 Anthropic/Claude 目标请求的请求体或 SSE/JSON 响应体。
- [ ] 普通 run 的默认行为不被破坏；`SAVE_FULL_FLOWS=0` 时普通 run 仍只保留摘要。
- [ ] run 详情能显示该 run 是分析抓包模式，并能看到抓包文件入口或文件列表。
- [ ] 敏感 header 在 UI/索引预览中被脱敏；原始完整数据只作为本地文件保存。
- [ ] 后端 lint/语法检查通过，前端基础交互可手动验证。

## Assumptions

- Claude Code 当前仍未做 certificate pinning，现有 MITM 链路能解密目标 HTTPS 流量。
- 捕获对象是用户本人授权账号和本地运行环境中的请求，用于调试兼容性与版本差异。
- 初版只支持一次选择一个 topic 和一个账号，不支持批量版本矩阵。
- 初版不做跨版本 diff UI，只产出后续可 diff 的 JSONL/JSON/flow 资产。

## Out of Scope

- 不修改 `/root/project/cc2api`。
- 不实现 Claude Code 多版本自动安装和矩阵对比。
- 不实现 WebUI 内大体积 body 全文浏览器。
- 不破解证书 pinning 或绕过远端服务访问控制。
- 不新增共享账号、规避风控、绕过封禁相关能力。

## Open Questions

- 无。

## Definition of Done

- PRD、design、implement 三件套完成并通过人工确认。
- 代码实现后运行必要的语法检查 / 单元或集成验证。
- 通过一次实际或模拟 run 验证抓包输出结构。
- 更新 README 或项目文档，记录使用方式和数据风险。
