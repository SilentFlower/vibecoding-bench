# Brief — 支持 HTTP 代理与一键填写

## Goal

- 让 vibecoding-bench 的账号代理配置支持 `http`、`socks5`、`socks5h`，并在添加/重授权账号时通过粘贴完整代理 URL 自动填充协议、地址、端口、用户名和密码。

## Scope

- 后端 `accounts` 表新增 `upstream_proxy_scheme`，并通过 `_SCHEMA` 与 `init_db()` 幂等兼容旧 SQLite。
- 后端 `AccountIn`、`LoginStartIn`、账号创建、登录 commit、同名重授权 update 写入代理协议。
- orchestrator 集中生成 sidecar 代理环境变量，并覆盖任务 run、继续对话、额度查询、OAuth 刷新、内嵌登录五条启动路径。
- sidecar 按 `UPSTREAM_PROXY_SCHEME` 生成 proxychains 出站类型：`http`、`socks5`、`socks5h`。
- WebUI 账号表、账号弹窗、paste-helper 文案和解析逻辑从 SOCKS5 专用扩展为通用代理 URL。

## Non-Goals

- 不支持 `https://proxy:443` 这种 TLS-to-proxy 代理入口。
- 不替换现有 tun / hev-socks5-tunnel / mitmproxy / proxychains 透明代理架构。
- 不改 `cc2api` 子模块的独立 `proxy_url` 路径。
- 不把现有 `upstream_socks5_*` 字段整体重命名为 `upstream_proxy_*`。

## Key Context

- 当前 WebUI 已有 SOCKS5 URL 粘贴辅助，但只支持 `socks5://` / `socks5h://`：`webui/index.html:375`、`webui/app.js:181`、`webui/app.js:231`。
- 当前账号表只有 `upstream_socks5_host/port/user/pass`，没有协议字段：`orchestrator/main.py:558`。
- 当前所有 sidecar 启动路径都传 `UPSTREAM_SOCKS5_*`：`orchestrator/main.py:1297`、`orchestrator/main.py:1523`、`orchestrator/main.py:1637`、`orchestrator/main.py:1877`、`orchestrator/main.py:2209`。
- 当前 sidecar 固定生成 proxychains `socks5` 出站配置：`images/sidecar/start.sh:46`。
- SQLite 新增列必须 `_SCHEMA` + `_ensure_column()` 双写；前端保持三静态文件零构建。
- proxychains HTTP 代理语义是 HTTP CONNECT；用户已确认只需要 `http://`，不需要 `https://proxy`。

## Acceptance

- 粘贴 `http://user:pass@proxy.example.com:8080` 自动填入协议 `http`、host、port、user、pass。
- 粘贴 `socks5h://proxy.example.com` 自动填入协议 `socks5h` 和默认端口 `1080`。
- 重授权已有账号时能展示并提交保存的代理协议。
- HTTP 代理账号在登录 session、任务 run、继续对话、额度查询、OAuth 刷新中都会让 sidecar 生成 `http` 出站配置。
- 老账号缺失协议时仍按 SOCKS5 运行。
- 粘贴 `https://proxy.example.com:443` 不会被当成可用协议自动提交。
- 通过 `python3 -m py_compile orchestrator/main.py`、`bash -n images/sidecar/start.sh`、`node --check webui/app.js`。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `task.py start`，然后进入 `trellis-route(implement)` 选择实现路线。
