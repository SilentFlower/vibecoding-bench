# v3 任务 TLS 透传与账号画像校正 — 技术设计

## 1. 边界与数据流

固定账号容器继续承载账号 HOME、CLI、账号发送器、网络出口和执行目录，但网络监听从单一 Recorder 拆成三种显式模式：

```text
Claude Code / tools
  -> tun0 -> hev-socks5-tunnel -> 127.0.0.1:8080
      passthrough -> raw SOCKS relay -> HTTP/SOCKS account proxy -> destination TLS
      quota       -> mitmdump + Recorder -> proxychains -> account proxy
      capture     -> mitmdump + Recorder + full flow -> proxychains -> account proxy

cc2api gateway -> account-sender -> account proxy -> Anthropic
```

passthrough relay 只实现 SOCKS5 CONNECT 入站、HTTP CONNECT 或 SOCKS5 上游握手和双向字节复制，不解析 TLS/HTTP。`hev`、强制默认路由和代理服务器 host route 保持现状，因此 CLI 不能从 eth0 直连业务目标。账号发送器继续显式使用自身 `proxy_url`，不经过本地 8080。

## 2. 网络模式契约

新增稳定枚举 `NetworkInspectionMode = passthrough | quota | capture`，只在调度器生成，写入 `/run/v3/context.json`。`v3-network-context` 在 `network.lock` 内：

1. 核对 context 的 mode/source。
2. 停止并等待上一监听进程，清理旧 PID/ack。
3. `passthrough` 启动 raw relay；`quota`/`capture` 启动 mitmdump 与 Recorder。
4. 新监听就绪后原子写 `context-ack.json`，包含 mode、source 和监听进程类型。
5. 调度器读取回执并逐字段匹配，之后才启动 CLI exec。

默认 idle/login 模式为 passthrough。普通 run 固定 passthrough；完整抓包固定 capture；手动额度查询固定 quota。养号在已有可信低额度时 passthrough，只有 `warmup_sample_required` 的单次执行使用 quota，Recorder 按原协议采样并暂停，后续恢复使用 passthrough。

passthrough 不加载 Recorder addon，不设置 `NODE_EXTRA_CA_CERTS`、`SSL_CERT_FILE`、`REQUESTS_CA_BUNDLE`、`CURL_CA_BUNDLE` 或 `GIT_SSL_CAINFO`，账号镜像也不把 MITM CA 加入系统信任。quota/capture 才把持久 CA 显式传给对应 CLI exec。网络监听退出由 PID1 标记 CLI 网络不健康；下一作业先对账，不能回退直连。

## 3. Raw relay

在账号镜像增加受测的 Python asyncio relay，避免新增未固定版本的第三方二进制。它包含：

- SOCKS5 无认证入站，仅接受 CONNECT。
- HTTP 上游代理的 Basic 认证和 CONNECT 状态校验。
- SOCKS5/SOCKS5H 上游的用户名密码认证与 CONNECT。
- IPv4、IPv6、域名地址编码；连接、握手和空闲超时。
- 双向流复制、半关闭和取消收口；日志只记录错误类别和是否配置代理，不记录地址、账号或认证信息。

代理配置由账号容器已有环境提供。配置了代理却无法握手时返回 SOCKS 失败并结束连接；只有明确空代理的测试环境允许直连，生产账号创建仍要求既有代理规则。

## 4. 画像 v2

新增 v3 专用 profile helper，返回：

```json
{
  "profile_version": 2,
  "hostname": "12 lowercase hex",
  "mac": "locally administered unicast",
  "machine_id": "32 lowercase hex",
  "tz": "America/Los_Angeles",
  "lang": "en_US.UTF-8",
  "mem": "1536m",
  "swap": "2048m"
}
```

随机字段分别调用 `secrets.token_bytes()`，不共享 seed。时区到 locale 使用单一映射 helper；显式账号时区在 generation=0 时同时校正 tz/lang。旧 JSON 无版本视为 profile v1，仅展示 legacy，不自动改变。

项目目录仍落在环境专属宿主目录，但容器内使用 `/home/node/projects/project-<opaque>`；opaque 由随机环境秘密与 run ID 做不可逆摘要，只用于路径，原 run ID 不进入容器 cwd。worker 控制状态移到 `/run/v3/jobs/<handle>`；对外 transcript/status API 继续从既有证据入口读取，不暴露迁移细节。

## 5. 显式 reprofile

环境维护增加 `reprofile`。后端在 owner/profile/environment 锁序下重读并验证：未绑定、无 task/run、无 identity.json、无登录草稿/提交、无 job/API 连接、容器可安全停止。通过后：

- 删除旧容器和网络/CA/执行临时产物，保留 HOME、workspaces 与账号代理。
- 生成 profile v2，更新 fingerprint，状态写为 `profile_reauth`，不改变账号 enabled。
- 普通 `ensure()` 遇到该状态失败关闭；登录恢复路径显式允许创建新画像容器。
- 重授权提交完全成功后清除门禁；取消或未知提交继续保持。

账号页/环境页只在可校正时显示入口，并明确“校正后必须重新登录”。生产只对 `10-13` 执行，执行前使用 v3 停机备份；OAuth 交互由用户完成。

## 6. 阈值与绑定解耦

`WarmupConfigIn.cc2api_account_id` 改为 `Optional[int]`。后端先解析当前绑定：

- 请求非空 ID：沿用现有绑定/切换核验。
- 请求为空且已有绑定：保留已有绑定。
- 请求为空且无绑定：只允许 `enabled=false`，保存间隔和显式阈值字段。

SQL 不再无条件写 `cc2api_account_id`；阈值字段仍通过 `model_fields_set` 区分省略与 null。前端下拉取消 HTML `required`，未绑定时显示说明并禁用定时养号开关，阈值输入保持可编辑。

## 7. 发布、验证与回滚

同批 control/account 镜像携带新 context/relay/profile 代码。验证先使用本地 HTTP/SOCKS 代理和 TLS 服务器证明 passthrough 字节保真，再验证 quota/capture 仍可解密。生产升级前停止 v3 并备份；升级后先验证空合成环境，再对 `10-13` 执行 reprofile。

回滚前不得让 profile_reauth 环境运行旧镜像。若用户尚未重授权，可恢复升级前 DB/HOME 备份及上一批双镜像；若已经重授权，优先保留新 HOME 并只在离线副本核对兼容，不能直接覆盖新凭据。

## 8. 取舍

- 自建小型 raw relay 增加一段网络代码，但它只处理标准代理握手和字节复制，避免普通任务依赖 MITM TLS 栈或引入大型第三方代理二进制。
- 普通任务失去被动 quota header，换取原生 TLS；现有 fail-closed 阈值与手动查询入口承担数据新鲜度。
- 现有账号不自动迁移，避免“升级即换设备”；代价是每个 legacy 账号要显式判断是否适合校正。
