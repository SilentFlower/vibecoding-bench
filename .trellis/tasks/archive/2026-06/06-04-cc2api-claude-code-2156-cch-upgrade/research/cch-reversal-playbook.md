# Claude Code 2.1.156 CCH 逆向参考

## 目标

为后续 Claude Code 版本升级提供一份可复用的 CCH 定位流程。本文只记录方法、断点线索、算法结论和安全摘要，不记录 token、prompt、请求体全文或响应体全文。

## 最终结论

Claude Code `2.1.156` 的 CCH 仍然是请求体哈希：

```text
cch = xxhash64(final_json_body_with_cch_00000, seed) & 0xFFFFF
```

其中：

- 输入是最终发出的 JSON body 字节序列，但 billing 行中的真实 `cch=<5hex>` 要替换回 `cch=00000`。
- hash 算法是标准 `XXH64`。
- `2.1.156` seed 是 `0x4D659218E32A3268`。
- 输出取低 20 bits，格式化为 5 位小写十六进制。
- 旧版本 seed `0x6E52736AC806831E` 仍保留给旧 profile。

对抓包 run `46ba25a8d791` 的 16 条带 billing `/v1/messages` 样本复现结果为 `16/16` 命中。

## 关键误区

1. 不能只看 binary 中是否存在旧常量。`59cf53e54c78`、`cch=00000`、billing 模板和 `xxHash64` 字符串仍存在，但旧 seed 对 `2.1.156` 抓包为 `0/16` 命中。
2. 不能假设 macOS 的原地写 watchpoint 流程能直接套到 Linux x64。Linux x64 上早期 heap 副本的 `cch=00000` 写 watchpoint 不触发。
3. 不能把完整 HTTP request bytes 当输入。验证结果显示输入是 JSON body 字节，不包含 HTTP headers。
4. 不能用 compact JSON、key sort、删除 metadata、仅 system、仅 messages 等候选输入替代最终 body；这些候选都没有匹配。

## 推荐定位流程

### 1. 先做抓包离线排除

从 `http_capture.jsonl` 中抽取 `/v1/messages`，只输出安全摘要：

- body 长度。
- billing 行中的 `cc_version` 短值和 `cch` 短值。
- body hash。
- 是否含 `cch=00000` 替换后的 placeholder。

验证旧算法：

```python
body = body_text.replace(real_cch, "cch=00000", 1).encode()
cch = xxhash.xxh64(body, seed=0x6E52736AC806831E).intdigest() & 0xFFFFF
```

如果旧 seed `0/样本数` 命中，优先怀疑 seed 或最终写入点变化，而不是马上改序列化。

### 2. 检查 cc_version，避免和 CCH 混在一起

`2.1.156` 的 `cc_version` 后缀仍是：

```text
sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]
```

注意这里的索引是 JavaScript 字符串索引语义，不是 UTF-8 字节索引。中文或 emoji 会让旧的 byte index 实现出错。

主会话的输入来自内部 transcript 的首个非 meta user message，不一定等于最终 `/v1/messages` body 里的首条 user 文本；side query 样本更容易直接复现。

### 3. 用 dummy upstream 做受控运行

为了不使用真实 token，可以用：

- `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`
- dummy `ANTHROPIC_API_KEY`
- `--bare`
- `--no-session-persistence`
- 本地最小 SSE 服务

目标是稳定触发 `/v1/messages?beta=true`，确认进程最终发出的 body 里 CCH 已从 `00000` 变成非零。

### 4. 从 send 路径往上追 body

Linux x64 `2.1.156` 中，本轮定位到的关键点：

- `0x43c7150`：native socket send 包装。
- `0x2e05400`：HTTP raw request 生成函数。
- `r14 + 0x4a0`：JSON body 源指针。
- `r14 + 0x4a8`：JSON body 剩余长度。
- `r14 + 0x4d8`：已发送/偏移计数。

一开始误判为进入 `0x2e05400` 前 body 已经是非零 CCH；复核后确认：`0x2e05400` 入口 body 仍是 `cch=00000`，替换发生在该函数内部。

### 5. 定位替换函数和 seed

`0x2e05400` 内部会调用 `0x2e05b10` 生成 header/body 片段。该路径会：

1. 搜索 `/v1/messages`。
2. 在 body 中搜索 `cch=00000`。
3. 初始化 `XXH64` 状态。
4. 对整个 JSON body 进行 hash，body 中仍保留 `cch=00000`。
5. 取低 20 bits。
6. 写回 `cch=` 后面的 5 个字节。

本轮看到的写回点在 `0x2e06878` / `0x2e0687e` 附近。

seed 通过 `XXH64` 初始化状态反推：

```text
state+0x20 = 0x4D659218E32A3268
seed + PRIME64_1 + PRIME64_2 = 0xAE4FBA0790EAE83E
seed + PRIME64_2             = 0x101840560AFF1DB7
seed                          = 0x4D659218E32A3268
seed - PRIME64_1              = 0xAF2E18675D3E67E1
```

### 6. 做最终复现

复现脚本只需要读取样本 body，替换第一处真实 CCH 为 placeholder：

```python
import re
import xxhash

body = original_body_text
body = re.sub(r"cch=[a-f0-9]{5}", "cch=00000", body, count=1).encode()
h = xxhash.xxh64(body, seed=0x4D659218E32A3268).intdigest()
cch = f"{h & 0xFFFFF:05x}"
```

验收标准：

- 对同一版本抓包样本达到全量命中。
- 对旧 seed 明确不命中。
- 对本地 dummy 受控样本也能命中。
- 不依赖 prompt 原文输出；脚本日志只输出长度、hash、真实 CCH、计算 CCH 和是否命中。

## cc2api 实现映射

本次实现落点：

- `src/service/version_profile.rs`：集中维护 Claude Code `2.1.156` 指纹。
- `src/service/rewriter.rs`：
  - `CCH_ATTESTATION_SEED_2156 = 0x4D659218E32A3268`
  - `CCH_ATTESTATION_SEED_LEGACY = 0x6E52736AC806831E`
  - `compute_cch_attestation(body, version)`
  - `cch_attestation_seed(version)`
  - `compute_cc_version_suffix` 改为 JS 字符串索引语义。

测试覆盖：

- `cch_seed_is_versioned`
- `cch_rewrite_uses_2156_seed`
- `cch_rewrite_keeps_legacy_seed_for_old_versions`
- `cc_version_suffix_uses_string_indices`

## 后续版本升级建议

新版本升级时按这个顺序做：

1. 先从抓包做旧 seed 离线验证。
2. 再确认 `cc_version` 公式是否变化。
3. 如果 CCH 不匹配，优先定位最终 HTTP body 写回点，而不是猜 JSON canonicalization。
4. 找到 seed 后必须对真实抓包和 dummy 样本双重复现。
5. cc2api 中按版本 profile 选择 seed，不要全局替换旧版本行为。
