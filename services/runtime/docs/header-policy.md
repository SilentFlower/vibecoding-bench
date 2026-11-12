# 请求头策略

本文件描述调用方请求头准入合同，对应 src/control/header-policy.ts 和 src/runtime/293/preload.ts。

## 原则

调用方请求头采用精确协议白名单，匹配忽略大小写。名单外的代理、CDN、网关或客户端私有头以及未知协议扩展逐项删除，并记录字段名、动作和原因；新增协议字段须显式登记。

白名单约束调用方可带入原生构造的字段。运行时自行生成的鉴权、身份和传输头遵循其实际归属。HTTP 入站头与内部信封头使用相同策略，原始入站记录保持独立。

请求头转发策略与日志脱敏规则独立：允许转发不代表允许把秘密值写进日志。

## 处理顺序

1. 验证头名与头值格式，保留有序多值输入。
2. 解析 Connection 的全部值，删除其中声明的字段，再删除 Connection 本身。
3. 删除固定连接级字段和调用方鉴权字段。
4. 精确识别上下文及已登记协议字段；其余字段逐项删除，包含同名重复项。
5. 验证已登记单值字段的重复、冲突及不支持的上下文，将上下文交给官方构造流程。
6. 由运行时生成其拥有的字段，按原有同名覆盖及多值顺序合并已准入协议头。

## 字段归属

| 字段 | 行为 |
| --- | --- |
| Connection 及其声明的字段 | 删除 |
| Keep-Alive、Proxy-Connection、TE、Trailer、Transfer-Encoding、Upgrade | 删除或由实际发送连接重建 |
| Authorization、X-Api-Key、Proxy-Authorization、Cookie | 删除调用方值，上游凭据来自账号运行环境 |
| Host、Content-Length、Content-Encoding、Content-Type、Accept-Encoding | 由实际目标、正文和原生传输生成 |
| User-Agent、X-App、X-Stainless-*、X-Client-Request-Id | 使用实际运行时生成值，避免输入版本或重名请求标识覆盖原生值 |
| x-claude-code-request-class | 映射调用上下文，再由原生链路生成 |
| x-claude-code-agent-id、x-claude-code-parent-agent-id、x-claude-code-agent-type | 保留调用关联语义 |
| x-claude-code-session-id、x-claude-code-prompt-id | 与内部会话、metadata、billing 一起对齐 |
| anthropic-beta、anthropic-version | 交由版本适配器处理，不支持的组合明确报错 |
| Accept、Accept-Language、Cache-Control | 保留完整值和合法多值顺序，覆盖 SDK 同名默认值 |
| anthropic-dangerous-direct-browser-access | 保留调用方完整单值，覆盖 SDK 同名默认值 |
| x-claude-code-prev-tool-durations、x-claude-code-compaction、x-claude-code-context-compacted | 固定 293 已定义的可选协议字段，保留完整单值 |
| 其余调用方字段 | 删除，原因是未登记到协议白名单 |

匹配大小写无关，删除覆盖同名头的全部实例。多值按字段语义处理；冲突的单值上下文或原生接口无法正确表达的重复字段应明确报错，不能静默取最后一个值。

直接进入现有合并或版本适配分支的白名单为上述九个协议字段。六个上下文字段按专用分支处理。字段按精确名称登记，`anthropic-*`、`x-claude-code-*` 等前缀不作为整体放行规则。

`Forwarded`、`X-Forwarded-*`、`X-Real-IP`、`Via`、`X-Amz-Cf-*`、`CloudFront-*`、客户端追踪及自定义头均不属于该准入集合。请求头格式仍先校验，非法格式保持明确失败。上游响应头沿既有响应合同处理。

扩展头不能指定任意目标 origin、代理、凭据来源或运行时控制配置。

## 分类与关联

- 官方 293 的已知类别为 main、subagent、workflow、compaction、auxiliary、side_reply。
- 已有子代理、工作流或压缩语义时保留原类别，不统一改成 main。
- 类别、agent 类型、agent ID、父 agent ID、会话及 billing 子代理标记作为一组处理。
- 如需映射标识，须稳定映射整个关联链；不默认重铸全部标识。
- 普通 API 无来源分类时，可以建立桥接器自己的普通主调用上下文，日志标明来自默认值。
- 普通主来源为 repl_main_thread，human 只用于实际主会话用户输入；工具结果、代理和辅助消息不借用 human 来源。
- 当前版本不能表达的显式上下文明确拒绝，不靠改名掩盖。

子代理须提供 agentId，workflow 还须提供 workflowRunId。promptId 必须为 UUID；不提供时由桥接器生成。独立 root agentId 通过 context.agentKind=main 明示。main 与显式子代理上下文冲突时返回错误，不能猜测调用身份。

anthropic-version 必须与原生值一致。普通 API 的 anthropic-beta 只能要求本次原生构造已经生成的能力，无法表达的额外 beta 返回 422。已识别的原生 CC 入站按其原有分支保留入站 beta。

## 正文与最终发送

请求头白名单不决定哪些 JSON 字段可以丢弃。正文逐字段适配，无法支持的显式参数明确报告。

293 的 JS 参数可能仍含 cch=00000，原生链路会继续处理。此前的参数不能冒充最终正文，实际长度与编码由最终发送链路决定。

User-Agent 由原生 CLI 生成，不主动附加 SDK client-app。CLI 的交互请求构造与 -p 打印模式有不同提示词和上下文；仅出现 cc_entrypoint=cli 不能证明内容对齐。本机 TLS 接收端的 wire_final 样本与 cc_prepared、生产自动采集能力分别记录，历史样本保留原值。

## 规范依据

- [RFC 9110，第 7.6.1 节](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.6.1)：Connection 字段及连接级字段处理。
- [RFC 9112，第 6.3 节](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3)：消息长度和传输编码规则。
