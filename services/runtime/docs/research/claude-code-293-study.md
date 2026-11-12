# Claude Code 2.1.293 最小接入研究

研究日期：2026-11-05。本轮检查固定版本并执行隔离实验，没有修改官方程序、cc2api 产品代码或已暂缓的 V4 规划。

## 结论

可以围绕官方 2.1.293 增加结构化入参和响应适配层。已验证其原生程序支持通过 BUN_OPTIONS --preload 加载外部模块，也能从预加载模块导入内嵌的 API 客户端。因此原型可先使用预加载入口，无须先修改 ELF 文件或重新打包字节码。

但 JS 层截获的请求仍可能包含 cch=00000。本地接收端实测确认，官方原生发送链路会在更晚的位置补齐 CCH。因此应区分“交给原生发送器的参数”和“实际出站正文”。

## 固定基线

- 安装包：@anthropic-ai/claude-code@2.1.293。
- 程序：/root/.nvm/versions/node/v22.23.4/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe。
- 程序大小：252755128 字节。
- SHA256：8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978。
- 实验前后 SHA256 相同。
- 程序包含 Bun 运行时、字节码及可读的分块 JS。下述函数名是该版本的内部混淆符号，不是稳定公共 API。

manifest.json 保存提取片段的原文件偏移、长度和 SHA256。source-*.formatted.js 仅由 Bun.Transpiler 重新排版，分析时未执行这些提取文件。

## 已定位的调用边界

| 边界 | 官方 293 位置 | 含义 |
| --- | --- | --- |
| 结构化模型调用 | source-392.formatted.js:70597，K_t | 接收 messages、systemPrompt、thinkingConfig、tools、signal、options，内部进入 kon |
| 最终请求对象构造 | 同文件 71739，TTe/BOn；71887，oc | 汇总模型、消息、system、工具、metadata、thinking、缓存及 beta 等字段 |
| SDK 调用 | 同文件 72731 | pl.beta.messages.create(...).withResponse() |
| 客户端构造 | source-277.formatted.js:17583，yN | 接收内部 fetchOverride，构造原版 SDK 客户端 |
| HTTP 参数包装 | 同文件 17990，a7 | 请求头、请求跟踪、压缩及响应观察等逻辑 |
| 默认发送链路 | 同文件 17325，Ree，再到 EI/pFn | 默认原生发送路径；独立 FetchSession 的选择还位于其他片段 |
| billing 生成 | source-164.formatted.js，Kso，正文位于第 38 行 | 生成归因文本和 CCH 占位符 |
| system 包装 | source-277.js，Q8o/iN | kon 内部调用 Q8o 并生成 billing；外部不能先封装一遍再交给 K_t |
| 用户消息实体 | source-392.formatted.js:114120，Re | API 消息需要转换为 CC 内部实体，不能把整个 JSON 当作一段 prompt |
| assistant 消息实体 | 同片段，RAn/Kc | 构造 CC 内部 assistant 消息，历史工具调用也需要相应映射 |

K_t 的实际入口接受一个包含 messages、systemPrompt、thinkingConfig、tools、signal、options 的对象。API 的 tools 与 CC 内部工具对象并非相同接口；293 代码中另有 options.extraToolSchemas 等入口，仍需逐字段确认适配合同。

## 运行验证

所有 CC 实验都在新的网络命名空间中运行。环境变量采用显式白名单，HOME 和 CLAUDE_CONFIG_DIR 指向新的空目录，只提供合成 API key。未加载真实账号凭据，未向真实 Anthropic 服务发送请求。

1. 原版 --version 返回 2.1.293 (Claude Code)。
2. 添加 BUN_OPTIONS=--preload 后，外部预加载脚本确实执行。
3. 预加载脚本成功导入 /$bunfs/root/chunk-aqh2c7wz.js，其中 yN 和 Ree 都是函数。
4. 正常运行原版 -p，在 JS 发送位置记录请求，使用合成 SSE 返回。CC 成功输出 CC293_OFFLINE_OK，只有一次模型请求。
5. 本地 CONNECT/TLS 接收端返回合成 SSE。默认发送与预加载拦截后调用原生 fetch 的两组实验，均成功输出 CC293_WIRE_OK。
6. 拦截器拿到了 HTTP 200、响应头、完整 SSE 和 message_stop，CC 随后正常消费了该响应。

原版构造的模型请求包含：

- User-Agent: claude-cli/2.1.293 (external, sdk-cli)。
- x-claude-code-request-class: main。
- 原版生成的 session-id、prompt-id、request-id。
- x-stainless-package-version: 0.128.0。
- 原版 system 中的 billing、客户端说明及缓存标记。

这证明原版主调用链不要求将请求固定为 vm2api 的 agent:kin/subagent 路径，但尚未验证任意 API 入参的完整桥接。

## CCH 的关键实验

| 实验 | JS 拦截点 CCH | 本地接收端 CCH | 独立复算 |
| --- | --- | --- | --- |
| 未增加预加载的默认发送 | 未截取 | e40d5 | e40d5，一致 |
| 预加载后调用原生 fetch | 00000 | 0231a | 0231a，一致 |

第二组发送前后正文均为 2230 字节。将 CCH 值归零后逐字节比较完全一致：本次变化只发生在 CCH 的五个字符。

独立复算调用系统 libxxhash.so.0，依据项目已有的 293 投影规则：所有精确 model 字符串字段置空、移除根级 max_tokens、billing CCH 归零，使用已验证 seed，再取低 20 bit。复算前确认 Python 对原文的 JSON 往返逐字节相同，避免重序列化差异污染结论。

证据文件：

- baseline.wire.json：默认发送的本地接收记录。
- preload-native.before-fetch.jsonl：JS 拦截点正文及返回的原始响应。
- preload-native.wire.json：原生发送后的本地接收记录。
- cch-independent-check.json：两组独立复算结果。
- offline-fetch.jsonl、offline-run.stdout.jsonl：纯本地合成响应实验。
- local-wire-probe.py、preload-native.mjs：本地接收实验脚本。

不同实验的 session-id、prompt-id 等不同，因此不同 CCH 值本身不代表内容异常；关键比较是同一次请求的 JS 参数与接收正文。

## 适合继续验证的最小方案

    API 入参
      → 薄适配层：转换内部消息实体、保留调用方工具语义
      → 官方 293 的初始化、system 构造及结构化模型调用
      → 内部 fetchOverride：记录发送参数并观察原始响应
      → 默认 Ree / 原生发送链路：完成最后处理及发送
      → 上游原始 status / headers / SSE 返回 cc2api

优先通过内部 fetchOverride 接入，并继续调用官方默认发送链路。当前实验的全局 fetch 替换用于证明机制；它会影响 pFn 对默认 fetch 与独立 FetchSession 的选择，未经对照不应直接视为生产实现。

如果一定由 Rust 发出最后一跳，需要另外取得原生处理后的正文，或者由明确受测的逻辑完成最终处理。把 JS 拦截点的占位正文直接交给 Rust，不等于复用了全部官方生成链路。

API 适配还需要明确只执行一轮模型调用，并把 tool_use 交回 API 调用方。CC 的 --output-format stream-json 是 CC 事件格式，不能直接等同于上游原始 SSE。

## 首版实现补充验证

结构化调用前必须执行 context.Nst()，再通过 state.t_(sessionId, 'resume') 进入对应原生会话。Re/Kc 生成内部消息实体，assistant 历史保留实际模型；K_t 内部会生成 billing 和 system 包装。

K_t 的原生调用固定使用流式接口。首版先在其内部 fetchOverride 中取得构造结果并在发送前中止，再使用同一个官方模块的 yN 客户端和 Ree 默认发送路径执行一次实际请求。第二阶段保留明确的 stream 标志，通过 asResponse 独占读取上游响应；SDK 不能提前消费错误正文。全局 fetch 保持原状。

主会话、子代理、主代理与子代理压缩、workflow、auxiliary、side_reply、工具及 thinking 签名历史、adaptive thinking、effort、非流式 JSON、HTTP/SSE 错误均纳入 tests/native/native.test.ts 的无外网回环测试。测试接收端独立计算 CCH，并比较中间与最终正文；这种测试接收能力没有写成生产 wire_final 采集能力。

本文前面的原型证据路径属于当时的临时实验目录，未将专有提取源码收入仓库。可重复执行的首版验证入口为 bun run test:native，二进制映射位于 src/runtime/profile.ts。

## 当前验证范围

- 已验证：固定 293 的外部注入、内嵌模块访问、原版请求组装、响应截取、原生 CCH 最终处理。
- 已实现并以合成数据验证：受支持 API 字段的结构化适配、工具及 thinking 历史、串行会话、逻辑响应字节、取消与有界背压、日志持久化和页面。
- 尚未验证：完整 Messages API 兼容、OAuth 真实账号路径、跨账号并发、生产流量及最终发送位置采集。
- 本地 TLS 夹具没有用于判断真实服务端风控，也没有建立“改用此模式会减少封号”的因果结论。
- 本轮没有恢复 V4，没有变更账号、服务或生产配置。

参考：[Bun 的 BUN_OPTIONS 文档](https://bun.sh/docs/runtime/environment-variables)。293 兼容性以本轮本地实测为依据。
