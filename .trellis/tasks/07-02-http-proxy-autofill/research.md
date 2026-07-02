# HTTP 代理支持研究

## 结论

- 本次 MVP 可以沿用现有 sidecar 架构和 `proxychains4`，不需要替换为 mitmproxy upstream mode 或新增代理库。
- proxychains-ng 的 HTTP 代理路径会向上游代理发送 `CONNECT <host>:<port> HTTP/1.0`，符合“HTTP 代理承载 HTTPS 目标流量”的常见语义。
- 本任务不支持 `https://proxy:443` 这种 TLS-to-proxy 入口；用户已确认 `http://` 即可。

## 证据

- 本仓现有 sidecar 固定写出 `socks5 ${UPSTREAM_HOST_IP} ${UPSTREAM_SOCKS5_PORT} ...`：`images/sidecar/start.sh:46`。
- proxychains-ng upstream `src/core.c` 的 `HTTP_TYPE` 分支生成 `CONNECT ... HTTP/1.0` 请求，并在 2xx 响应后建立隧道：<https://github.com/rofl0r/proxychains-ng/blob/master/src/core.c>。
- proxychains-ng 默认配置示例的 `[ProxyList]` 以 `<type> <host> <port> [user pass]` 形式配置代理：<https://github.com/rofl0r/proxychains-ng/blob/master/src/proxychains.conf>。

## 设计影响

- sidecar 只需要新增一个协议环境变量，例如 `UPSTREAM_PROXY_SCHEME`，并把 ProxyList 首列从固定 `socks5` 改为 `http` / `socks5` / `socks5h` 映射。
- orchestrator 继续传 host/port/user/pass 字段，同时对老账号缺失协议时按 `socks5` 默认。
- WebUI 的一键填入需要解析 `http://`、`socks5://`、`socks5h://`，显式拒绝或忽略 `https://`。
