# 本地 TLS 与池 Messages 验证

测试路径为“HTTP 入站 → 固定 CC → 本地 CONNECT → 独立 Node TLS 接收端 → 池 Messages”。CC 保持原生目标和模型装配，只有第二段使用池 Base URL、池 Key 和 deepseek-flash。没有 OpenAI 协议转换。

需要 Linux 的网络命名空间权限、Bun、Node、openssl、ip，以及已接纳的固定 293 二进制。报告页面验收另需 Playwright 可用的 Chrome。此工具不修改生产配置、运行时源码或池配置。

## 离线验证

```bash
bun run test:pool --binary /absolute/path/to/registered/claude --output artifacts/pool-offline-new --serve 8789
```

缺省模式只连接无外网空间内的本机假池，CC 驱动另处于仅有 lo 的嵌套网络空间。合成 Key、HOME/config、TLS 证书在独立临时目录中，结束后清理。普通单元、集成和构建不会读取真实池配置。

离线场景覆盖原生主请求、子代理、普通 API、preserve/sub2api、工具历史、JSON/SSE、取消、401/429/500、重定向、缺少终态、SSE error、超时、密钥回显及超过预览上限的响应。分别指定官方原版和已接纳精简版运行；不因测试而重建或重新授信运行时。

## 显式真实池

将下列内容写入权限 0600 的独立 env 文件；不能把 Key 作为命令行参数。文件只解析赋值，不执行 shell。

```dotenv
CCRB_TEST_POOL_BASE_URL=https://pool.example/v1
CCRB_TEST_POOL_API_KEY=由操作者填写
```

兼容现有 `PROJECT_REQUESTER_BASE_URL` / `PROJECT_REQUESTER_API_KEY`；两种来源冲突时拒绝启动。模型字段和 fallback 不读取，固定使用 deepseek-flash。

池 Key 仅支持 4–4096 位 ASCII 字母、数字和 `._~-`。含引号、反斜杠、空白、Unicode 或其它字符的配置在发送前拒绝，错误不回显原值，避免 JSON 转义后的错误回显绕过原文脱敏。

真实池 Node 端沿用宿主 `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY`（兼容同值小写键），通过 Node `--use-env-proxy` 启用。需要本机 Node 支持该选项；无此选项时启动失败、零模型发送。仅接纳无 URL 凭据的 HTTP(S) 代理，大小写配置冲突时拒绝。代理配置不传给 CC 驱动；CC 的代理仍是隔离空间内的本地采集器。离线模式不继承宿主代理。

```bash
bun run test:pool --live --pool-env /protected/path/pool.env --binary /absolute/path/to/registered/claude --output artifacts/pool-live-new
```

首次真实验收固定三个串行场景：原生主请求 JSON、原生子代理 SSE、主动取消 SSE。每次 max_tokens=128，池预算 30 秒，CC 预算 45 秒。首个失败立即停止，没有自动重试、跟随重定向、换模型或删除业务字段。池拒绝字段或鉴权时保留实际响应；不能以离线成功替代真实兼容结论。

`artifacts/pool-tls-forwarder-live-first-run.json` 以排他方式创建，发送前预留场景，防止误重跑突破首次预算。账本已经存在时不会再次发起真实推理；本轮验收不删除或重置它。中途退出时预留数是保守上界，实际尝试数以已收到的回执为准。

需要单独的新一轮验收且已明确其预算时，显式增加 `--live-run <ID>`；ID 限 1–64 位 ASCII 字母数字、下划线及连字符，首字符必须为字母数字。它使用独立的 `artifacts/pool-tls-forwarder-live-<ID>.json`，同名轮次依然排他拒绝。每轮固定最多三次、串行、128 tokens、首错停止，不会自动创建下一轮；默认仍使用原 first-run 账本。

## 报告

```bash
bun run test:pool --report-only artifacts/pool-live-new --serve 8789
bun run test:pool:page artifacts/pool-offline-new
```

只读模式仅开放 `index.html` 和 `report.json`，刷新不重新推理。`--serve` 与离线测试组合时，场景结束后由宿主开放报告，旧的 8787/8788 页面不受影响。

每个场景独立显示实际 HTTP 入站、CC 中间值、Node TLS 实收的 CC 最终出站、池客户端组装参数、池响应和调用方响应。原始有序头由 Node 的 rawHeaders 采集并在启动时自检。原生 CCH 只在实收后独立核验，不生成或补写出站值。池参数中的头部属于提交给客户端的组装表示，不能称为池端抓到的网络头。

正文预览最多 1 MiB，请求上限 2 MiB。完整响应继续转发并计算原始字节哈希；脱敏、截断和采集缺失单独标注。响应属于 fetch 读取的逻辑字节，可能已经解压。HTTP 200、完整 EOF、合法 Messages 终态是不同结果，SSE error 和缺少 message_stop 均不可写成成功。

`forwarding.upstreamStatus` 只有收到池响应头后才有值；未收到时为 null，`poolResponse` 也为 null。本地合成的 400/502 只在 `forwarding.localStatus` 与调用方响应中展示，不冒充池状态。`forwarding.outcome` 记录传输结果，场景 `state` 使用产品 RequestTrace 的响应语义。异常只保存白名单错误码和受控说明，不能把含 URL、头部或 Key 的任意异常 message 写入报告。

池 Key 只进入宿主控制端和 Node 转发器；CC 使用合成凭据。隔离驱动日志模式 off，防止不了解池 Key 的生产日志器先保存错误回显。私有回执由宿主再次脱敏后才写报告；秘密、证书和配置不进入 Git。

本工具证明测试接收点实际观测的两段请求与响应。生产 `nativeFinalCapture` 仍为 false；池成功不代表 Anthropic 鉴权、付费缓存命中或完整上游兼容已经验证。
