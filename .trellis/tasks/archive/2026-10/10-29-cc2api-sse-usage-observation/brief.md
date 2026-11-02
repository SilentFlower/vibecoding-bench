# Brief — cc2api：SSE事件与压缩长流统计修复

## Goal

- 修复合法 SSE 和压缩长流的用量／诊断漏记，让客户端继续收到原始响应。

## Scope

- R4-01：多 data、LF／CRLF／CR、跨块与 BOM 的完整事件解析。
- R4-02：gzip／x-gzip、deflate、br、zstd 及预算内编码链的增量统计，覆盖用量、诊断和缓冲入口。

## Non-Goals

- 保活、补结束帧、TTFT 定义、请求改写、CCH、缓存锚点和自动遥测规则；不增加设置、迁移或部署。

## Technical Overview

- 原始响应片段照常转发；统计副本逐层增量解码，小块输出直接进入事件解析器，不缓存整条回复。
- 完整事件合并用量，结束时校验压缩完整性；正常结束、错误与取消都只收口一次。

## Context & Decisions

- SSE 事件边界遵循 [WHATWG 规范](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)；保留现有累计最大值、真实零值、缓存分项与部分费用语义。
- JSON／单行／单事件各保留 1 MiB 上限；最多 4 层编码，br／zstd 每层窗口至多 16 MiB。复用现有依赖，两套观察器保持独立生命周期。

## Risks

- 少见 deflate 头冲突或晚期解码失败保守标 partial，保留已知用量，原响应照常转发。
- 同步解码有 CPU 开销；按源码估算，极端四层最大窗口 br 的两套观察器约需 160 MiB codec 工作区，另有解析等开销。

## Acceptance

- 各种 SSE 排版与编码产生一致摘要；分别验证解压后及原始压缩字节超过 1 MiB 的长流。
- 实际 Gateway＋临时数据库验证正常／取消／错误：响应字节和编码头匹配上游，用量只写一次，不新增上游请求。
- 超限、损坏和截断仍受控标 partial；格式、全量及 CCH／请求压缩／保活／费用回归通过。

## Next Step

- 确认后，先实现共享的有界 SSE 事件观察器。
