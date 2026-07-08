# 支持 HTTP 代理与一键填写

## Goal

让 vibecoding-bench 的账号代理配置同时支持现有 SOCKS5 和新增 HTTP 代理，并在添加或重授权账号时允许用户粘贴一整条代理 URL 自动填充协议、地址、端口、用户名和密码，减少手动拆字段出错。

## Confirmed Facts

- 用户确认需求范围是“代理协议支持 HTTP/HTTPS”和“添加代理时一键填写”，不是 Agent 服务本身改成 HTTP API。
- 当前 WebUI 已有 SOCKS5 URL 粘贴辅助，但只支持 `socks5://` / `socks5h://`，并只回填 `upstream_socks5_host`、`upstream_socks5_port`、`upstream_socks5_user`、`upstream_socks5_pass` 四项：`webui/index.html:375`、`webui/app.js:181`、`webui/app.js:231`。
- 当前账号表只保存 SOCKS5 字段，没有协议字段：`orchestrator/main.py:558`。
- 当前任务运行、继续对话、额度查询、OAuth 刷新和内嵌登录都会把账号字段作为 `UPSTREAM_SOCKS5_*` 环境变量传给 sidecar：`orchestrator/main.py:1297`、`orchestrator/main.py:1523`、`orchestrator/main.py:1637`、`orchestrator/main.py:1877`、`orchestrator/main.py:2209`。
- 当前 sidecar 启动脚本要求 `UPSTREAM_SOCKS5_HOST` / `UPSTREAM_SOCKS5_PORT`，并用 `proxychains4` 固定生成 `socks5` 出站配置：`images/sidecar/start.sh:5`、`images/sidecar/start.sh:15`、`images/sidecar/start.sh:46`。
- `cc2api` 子模块已有独立 `proxy_url` 路径，交给 reqwest 支持 HTTP/SOCKS；本任务聚焦 vibecoding-bench 的主 WebUI / orchestrator / sidecar 链路，不改 `cc2api`。
- 用户确认本次不需要 `https://proxy:443` 这种 TLS-to-proxy 入口；MVP 支持 `http://` HTTP CONNECT 代理和现有 `socks5://` / `socks5h://`。
- proxychains-ng 的 HTTP 代理路径通过 `CONNECT host:port HTTP/1.0` 建隧道，能覆盖本次 HTTP 代理诉求；研究记录见 `research.md`。

## Requirements

- R1：账号代理配置必须新增“代理协议”语义，支持 `http`、`socks5`、`socks5h`，默认兼容已有账号的 SOCKS5 行为。
- R2：添加账号和重授权账号时，用户可以粘贴完整代理 URL 自动拆分到协议、host、port、user、pass。
- R3：URL 解析至少支持无凭据和有凭据两类格式，例如 `http://host:port`、`http://user:pass@host:port`、`socks5://host:port`、`socks5h://user:pass@host:port`；`http` 默认端口为 `8080`，SOCKS 默认端口为 `1080`。
- R4：任务运行、继续对话、额度查询、OAuth 刷新、内嵌登录必须使用账号保存的代理协议启动 sidecar。
- R5：已有只配置 SOCKS5 字段的数据库数据必须无迁移断点，升级后继续按 SOCKS5 运行。
- R6：UI 文案应从纯 `socks5_*` 概念收敛为更通用的代理配置，同时保留后端字段兼容或提供明确迁移。
- R7：本次明确不支持 `https://proxy:443` 作为代理入口，也不引入新的代理库或替换透明代理/MITM 架构。

## Acceptance Criteria

- [ ] 新增账号时粘贴 `http://user:pass@proxy.example.com:8080` 会自动填入协议 `http`、host `proxy.example.com`、port `8080`、user `user`、pass `pass`。
- [ ] 新增账号时粘贴 `socks5h://proxy.example.com` 会自动填入协议 `socks5h`、host `proxy.example.com`、默认端口 `1080`。
- [ ] 重授权已有账号时，表单能展示并提交该账号保存的代理协议和代理字段。
- [ ] 使用 HTTP 代理的账号启动登录 session、任务 run、继续对话、额度查询和 OAuth 刷新时，后端传给 sidecar 的环境变量包含代理协议，sidecar 生成 `http` 出站配置。
- [ ] 未设置协议的老账号仍按 SOCKS5 运行，不要求用户重新添加。
- [ ] 前端 URL 解析失败时不破坏用户已手填的字段。
- [ ] 粘贴 `https://proxy.example.com:443` 不会被当成可用协议自动提交；用户需要改为 `http://` 或 SOCKS。
- [ ] 相关改动通过本项目可用的后端语法/启动校验、sidecar shell 语法校验和前端静态校验。

## Notes

- 这是跨 WebUI、orchestrator、SQLite schema 和 sidecar 启动脚本的任务，属于复杂任务；进入实现前需要补 `design.md` 和 `implement.md`。
- “HTTP 代理”在本任务中指 HTTP CONNECT 代理入口，仍可承载 HTTPS 目标站点流量；不是 `https://` scheme 的代理入口。
- 当前没有阻塞实现的开放问题。
