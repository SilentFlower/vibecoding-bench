# design.md

## Technical Design

### Scope

改造目标仍在 `/root/project/cc2api/src/service/rewriter.rs` 的 `/v1/messages` body 改写链路。设置入口沿用 `message_cache_control_rewrite`，新增一个独立策略值，暂定 `stateful`。该策略复用当前 `auto` 的 prefix 稳定化和断点安全规则，但增加会话状态和请求形态分类。

### 为什么旧 anchored 不够

旧 `anchored` 的核心是单一内存映射：

```text
account + session_id -> last_selected_block_fingerprints
```

它没有区分正常主线请求和异常内部请求。遇到 `76 blocks -> 567 blocks -> 78 blocks` 时，567-block 请求可能覆盖主线 anchors，下一轮 78-block 请求找不到这些位置，回到无状态选点。它也没有同一 session 并发写状态的覆盖保护。

### 数据结构

建议引入：

```text
StatefulCacheStore
  sessions: LruMap<SessionKey, SessionCacheState>

SessionCacheState
  normal_profile: Option<RequestProfile>
  normal_anchors: Vec<AnchorRecord>
  temporary_profiles: Vec<RequestProfile>
  generation: u64
  updated_at: Instant

RequestProfile
  block_count: usize
  message_count: usize
  tool_result_count: usize
  assistant_tool_use_count: usize
  last_user_text_hash: Option<String>
  tail_role_type: String

AnchorRecord
  fingerprint: AnchorFingerprint
  message_idx: usize
  block_idx: usize
  block_type: String
  context_hash: String
  selected_at_generation: u64
```

状态保存结构化 hash，不保存 prompt 原文。

### Request Classification

每次请求先计算 `RequestProfile`，与 `normal_profile` 比较：

* `NormalLinear`：block 数接近上次主线，例如增长不超过 3 倍，且绝对增长不超过 128；存在正常用户 turn；能复用至少一个旧 anchor。
* `TransientSpike`：block 数超过主线 3 倍且绝对增量超过 128，例如 `76 -> 567`。
* `ParallelSibling`：同一 session 短时间内出现不同 block_count 的并发请求，且其中一个接近主线。
* `Unknown`：无历史或无法判断，按保守 normal 初始化，但需要日志标记。

分类阈值应定义为常量并测试，后续可调。

### Selection Algorithm

1. 稳定化 prefix。
2. 清理根级、system、tools、messages 旧 `cache_control`。
3. 计算 profile 和 request class。
4. 若存在 `normal_anchors`，在当前 messages 中按 fingerprint 查找。
5. 对 `NormalLinear`：
   * 优先保留 1-2 个命中的旧 anchor。
   * 剩余 slot 按当前 auto 规则补 bridge / tail。
   * 选点后 promotion：更新 `normal_profile`、`normal_anchors`、`generation`。
6. 对 `TransientSpike` / 明显异常请求：
   * 可按 auto/rolling 临时选点，降低单次创建成本。
   * 不更新 `normal_anchors`。
   * 日志记录 `promotion=ignored_spike`。
7. 对 `ParallelSibling`：
   * 如果请求与主线接近且 anchor 命中，允许 promotion。
   * 如果请求与主线差异大，作为 transient，不覆盖。

### Fingerprint Matching

fingerprint 输入应剥离 `cache_control`，包含：

* message role
* block type
* canonicalized block JSON hash
* 前一个和后一个可见 block 的短 hash（可选，用于重复 block disambiguation）

匹配时优先精确匹配 full fingerprint；若失败，不做弱匹配，避免误锚定。

### Logging

新增 `cc2api::cache` 日志字段：

```text
mode="stateful"
session="..."
request_class="normal_linear|transient_spike|parallel_sibling|unknown"
block_count=...
normal_block_count=...
reused_count=...
selected_count=...
promotion="updated|ignored_spike|ignored_no_reuse|missing_session"
selected=[...]
```

### Rollout / Rollback

默认仍保持现有默认行为，不自动切换。用户可在设置页手动选择 `stateful`。出现异常时切回 `auto`、`rolling` 或 `off`。

## Rollout / Rollback

该策略只保存进程内 hash 状态，重启后自动冷启动。冷启动第一轮会按无状态选点创建缓存，后续请求开始复用。若命中表现不佳，可直接切回 `auto` 或 `off`。
