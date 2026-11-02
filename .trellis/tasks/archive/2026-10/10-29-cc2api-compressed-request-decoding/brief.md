# Brief — cc2api：压缩请求解码与重编码

## Goal

- 修复压缩请求正文与编码头错配，让现有身份、字段清理、Session 和 CCH 改写正常执行。

## Scope

- 通用 Gateway（Messages、遥测及其它转发）和 count_tokens；支持 gzip／x-gzip、deflate、标准 br、zstd 及有序叠加。

## Non-Goals

- 响应保活／响应解码、TLS、新版本画像、前端及设置不纳入本轮；不使用真实账号推理。

## Technical Overview

- 按实际 Content-Encoding 严格解码 → 执行既有逻辑 → 每次发送前按原编码链重压缩，并重新生成长度。未压缩请求保持原路径，重试及缓存继续使用逻辑正文。

## Context & Decisions

- 用户已选择出站跟随入站编码、由子 agent 实施。官方 v2.1.300 已确认大请求 gzip 行为覆盖遥测关闭场景。[发布记录](https://github.com/anthropics/claude-code/releases/tag/v2.1.300)
- 原字节及每层解码上限 10 MiB，最多 4 层／32 个列表片段，br／zstd 窗口最多 16 MiB；容许重压缩容器开销超过原读取上限。
- 未知编码返回 415，非法／无法完整解码返回 400，大小超限返回 413；入站拒绝先于账号相关副作用。

## Risks

- 编解码增加 CPU／内存；层数、窗口及大小限制会排除超范围合法流。保留编码方式和顺序，不承诺压缩字节或原生容器参数相同。

## Acceptance

- 实际 Gateway＋本地上游验证 CC／API、各入口、Session／CCH／字段清理／stream 三态，以及发送正文、编码头和长度一致。
- 覆盖损坏／超限／多值叠加、近上限重编码、401／signature／换号重试及缓存；入站拒绝零账号副作用、零上游请求。
- 未压缩与 R2／beta 回归、Rust 格式、全量及 CCH 测试通过；明确尚无 300 之后的新原生抓包。

## Next Step

- 确认后启动任务，交给实施子 agent 先补能复现旧缺陷的回归测试。
