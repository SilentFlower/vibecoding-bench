# 支持 HTTP 代理与一键填写 · 设计

## 架构边界

- WebUI：保留三静态文件结构，改账号弹窗的代理表单和粘贴解析函数，不引入构建工具或依赖。
- orchestrator：在 `accounts` 表和 DTO 中新增代理协议字段，兼容旧 SOCKS5 字段命名；集中生成 sidecar 环境变量，避免五处容器启动逻辑分叉。
- sidecar：保留 tun → hev-socks5-tunnel → mitmproxy socks5 inbound → proxychains 上游出站链路，只把上游 `ProxyList` 类型改为按账号协议生成。

## 数据模型

- 在 `accounts` 表新增 nullable 文本列：`upstream_proxy_scheme TEXT DEFAULT 'socks5'`。
- `_SCHEMA` 的 `accounts` 表声明包含新列。
- `init_db()` 使用 `_ensure_column(conn, "accounts", "upstream_proxy_scheme", "TEXT DEFAULT 'socks5'")` 兼容已有 `data/db.sqlite`。
- API 返回账号时自然包含 `upstream_proxy_scheme`，老行缺失时由数据库默认或后端归一化按 `socks5` 处理。

## API 合约

- `AccountIn` 和 `LoginStartIn` 新增 `upstream_proxy_scheme: Optional[str] = None`。
- 后端只接受 `http`、`socks5`、`socks5h`，空值默认 `socks5`。
- 保存账号、登录 commit、同名账号重授权 update 都写入协议字段。
- 仍保留 `upstream_socks5_*` 字段名作为兼容字段，避免一次性重命名打穿历史数据和前端调用。

## sidecar 合约

- orchestrator 传新环境变量 `UPSTREAM_PROXY_SCHEME`，同时继续传旧 `UPSTREAM_SOCKS5_*`，降低改动面。
- `images/sidecar/start.sh` 中新增协议归一化：
  - `http` → proxychains `http`
  - `socks5` → proxychains `socks5`
  - `socks5h` → proxychains `socks5`
- `https` 和未知值直接 fatal，避免用户以为已经支持 TLS-to-proxy。
- 默认端口由前端辅助提供；后端和 sidecar 对缺省端口仍按现有逻辑兜底为 `1080`，但 HTTP 表单粘贴会填 `8080`。

## WebUI 合约

- 账号表展示从 `host:port` 改为 `scheme://host:port`。
- 账号弹窗新增协议选择控件，选项为 `http`、`socks5`、`socks5h`。
- paste-helper 从 `parseSocks5Url/applySocks5Url` 泛化为 `parseProxyUrl/applyProxyUrl`。
- 粘贴 `http://user:pass@host:8080` 填协议、host、port、user、pass。
- 粘贴 `https://...` 返回 null，不覆盖已填字段。

## 兼容与迁移

- 已存在账号没有协议列时，`init_db()` 自动补列并设置默认 `socks5`。
- 已存在账号的 host/port/user/pass 字段不改名、不迁移数据。
- 新接口字段是新增字段；旧前端如果不传协议，后端按 `socks5` 保存。

## 取舍

- 不把字段整体重命名为 `upstream_proxy_*`，因为这会牵动 DB、API、历史数据和大量调用点；本次只新增协议字段，后续若要清理命名可单独做重构任务。
- 不支持 `https://proxy`，因为当前 proxychains HTTP 分支是明文 HTTP CONNECT；用户已确认本次只需要 `http://`。
- 不替换 mitmproxy upstream mode，因为现有 tun/DNS/worker 共享网络命名空间链路已经稳定，替换会扩大风险。

## 回滚

- 如果 sidecar 协议支持有问题，回滚 `images/sidecar/start.sh` 和 orchestrator 环境变量生成即可恢复固定 SOCKS5。
- 数据库新增列是兼容性变更，回滚代码后旧代码会忽略该列，不需要删列。
