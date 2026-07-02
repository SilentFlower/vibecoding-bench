# 支持 HTTP 代理与一键填写 · 实施计划

## 步骤

1. 后端数据与校验
   - 在 `accounts` schema 中新增 `upstream_proxy_scheme`。
   - 在 `init_db()` 补幂等 `_ensure_column`。
   - 增加协议归一化 helper，限制为 `http`、`socks5`、`socks5h`。
   - 更新 `AccountIn`、`LoginStartIn`、账号 insert/update/commit 逻辑。

2. sidecar 环境变量集中化
   - 在 orchestrator 中抽一个生成 sidecar 代理环境的 helper，避免五处重复拼 `UPSTREAM_SOCKS5_*` 时漏协议。
   - 替换任务运行、继续对话、额度查询、OAuth 刷新、内嵌登录的 sidecar environment。

3. sidecar 出站协议支持
   - `images/sidecar/start.sh` 读取 `UPSTREAM_PROXY_SCHEME`。
   - 按协议生成 proxychains `ProxyList` 类型。
   - 更新日志和错误消息，不再把所有上游代理都称作 socks5。

4. WebUI 表单与粘贴解析
   - `webui/index.html` 新增协议选择，文案从 socks5 URL 改为 proxy URL。
   - `webui/app.js` 展示 `scheme://host:port`。
   - 泛化 URL 解析函数，支持 `http` / `socks5` / `socks5h`，拒绝 `https`。
   - 重授权表单回填协议。
   - `webui/style.css` 注释从 SOCKS5 URL 改为 proxy URL。

5. 文档和验证
   - 如 README 中账号说明仍写“SOCKS5”，补充 HTTP 代理支持。
   - 运行后端语法校验、sidecar shell 语法校验和前端静态检查。

## 验证命令

```bash
python3 -m py_compile orchestrator/main.py
bash -n images/sidecar/start.sh
node --check webui/app.js
```

可选真跑验证：

```bash
docker compose up -d --build orchestrator sidecar worker
```

## 风险点

- sidecar 的 DNS ready 依赖代理出口可达；HTTP 代理不通时表现会和 SOCKS5 不通一样，需要错误消息指向代理协议/地址。
- proxychains `http` 只代表 HTTP CONNECT，不代表 `https://proxy`。
- 账号表新增列必须保证旧 DB 幂等升级，否则远程实例启动会失败。

## 回滚点

- `orchestrator/main.py` 中 schema/DTO/sidecar env 改动。
- `images/sidecar/start.sh` 中 proxychains 类型生成。
- `webui/{index.html,app.js,style.css}` 中表单和解析改动。
