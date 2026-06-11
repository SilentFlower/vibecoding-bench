# Claude Code 2.1.172 CCH 复核记录

## 样本

- 169 baseline：`data/flows/pingguo-1/2873/10f2065adf44`
- 172 Opus：`data/flows/pingguo-1/3075/a773a0d683a6`
- 172 Fable：`data/flows/pingguo-1/3078/715232eae9e8`
- 本地 binary：`@anthropic-ai/claude-code@2.1.172`，`claude --version` 输出 `2.1.172 (Claude Code)`。

本文只记录长度、命中数和算法结论，不记录 token、Authorization、Cookie、账号邮箱、完整 prompt 或响应正文。

## 运行期 seed 复核

按旧 2.1.156 playbook，在本地 dummy upstream 上运行 2.1.172，不使用真实 token。断到 native CCH 初始化点后，XXH64 state 仍为：

```text
seed + PRIME64_1 + PRIME64_2 = 0xAE4FBA0790EAE83E
seed + PRIME64_2             = 0x101840560AFF1DB7
seed                          = 0x4D659218E32A3268
seed - PRIME64_1              = 0xAF2E18675D3E67E1
```

结论：`2.1.172` 的 CCH seed 没变，仍是 `0x4D659218E32A3268`。

## 输入规则复核

对 `/v1/messages` 样本统一先把第一处 `cch=<5hex>` 替换回 `cch=00000`。

| 样本 | 完整 body | 去 `model` 值 + `max_tokens` | 再去 `fallbacks` |
| --- | ---: | ---: | ---: |
| 169 baseline | 25/25 | 0/25 | 0/25 |
| 172 Opus | 0/38 | 38/38 | 38/38 |
| 172 Fable | 0/23 | 1/23 | 23/23 |

Fable 的 1 条命中是 Haiku/title 探测请求，本身没有 `fallbacks`。22 条 `claude-fable-5` 主请求需要额外排除 top-level `fallbacks` 字段。

## 解释

新版看起来“奇怪”的原因不是 seed 随模型变化，而是 CCH 从“完整 body 指纹”变成了“忽略部分调度字段的 body 指纹”。被忽略的字段正好是客户端或服务端调度可能临时变化的字段：

- `model`：允许一次性模型覆盖或服务端模型选择不改变 CCH。
- `max_tokens`：不同模型族的 token 上限不同，排除后避免 CCH 跟随预算字段变化。
- `fallbacks`：Fable 主请求带 fallback 到 Opus 的候选，排除后 fallback 策略变化不影响 CCH。

请求体实际发送时这些字段仍存在；只是计算 CCH 时不参与 hash。旧版本 169 没有这个规范化，仍 hash 完整最终 body。

## 实现提示

cc2api 不能只把 seed 改掉。应新增 `2.1.172` 的 CCH 输入 profile，并保持 `2.1.156` / `2.1.169` 旧 profile 不变。裁剪必须基于最终序列化 body 字节，并且只裁剪 top-level 字段，避免破坏字段顺序和嵌套 JSON 内容。
