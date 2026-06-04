# CCH / cc_version 浅尝研究记录

## 样本来源

- 抓包 run：`46ba25a8d791`
- 抓包文件：`data/flows/auto-2/1887/46ba25a8d791/http_capture.jsonl`
- Claude Code 安装方式：远端 worker 使用 `npm install -g @anthropic-ai/claude-code@2.1.156`。
- 实际入口：`@anthropic-ai/claude-code/bin/claude.exe`。这里的 `.exe` 是 npm 包统一使用的 bin 文件名，不代表 Windows 可执行文件；Linux x64 包内该文件实际是 `ELF 64-bit LSB executable, x86-64`，约 230MB。
- 本地当前 `claude` 命令指向 `/root/.nvm/versions/node/v22.21.1/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`，版本为 `2.1.154`。前面用于浅尝分析的 `2.1.156` 样本保存在 `/tmp/claude-code-2.1.156.exe`，不是当前 global `claude` 指向的文件。
- 目前做的是 native binary 的 `strings` / byte search 浅查，不是源码级阅读；后续若要研究算法，需要围绕 binary 中的 bundle 字符串和函数边界继续反推。
- 2026-06-04 已把本机 global `@anthropic-ai/claude-code` 升级到 `2.1.156`；`claude --version` 输出 `2.1.156 (Claude Code)`，实际文件 SHA256 与 `/tmp/claude-code-2.1.156.exe` 一致。

## 抓包样本结论

- `/v1/messages` 共 17 条。
- 其中 16 条 system prompt 内包含 billing 行：
  - `x-anthropic-billing-header: cc_version=2.1.156.<suffix>; cc_entrypoint=cli; cch=<5hex>;`
- 1 条 haiku 极小请求没有 billing 行。
- `cc_version` 后缀分布：
  - `b94`：15 条，集中在同一个 Opus 会话中。
  - `b2a`：1 条，出现在 haiku 请求中。
- `cch` 分布：
  - 16 条 billing 请求全部为不同 5 位十六进制值。
  - 同一 Opus 会话中首条用户消息 hash 相同，但 `cch` 随上下文增长变化。

## 旧算法复现结果

用 cc2api 当前两段算法验证抓包：

- `cc_version` 后缀旧算法：固定 salt `59cf53e54c78` + 首条用户消息位置字节 + version → SHA256 前 3 位。
- `cch` 旧算法：将 body 中 `cch=<value>` 替换为 `cch=00000` 后，使用 seed `0x6E52736AC806831E` 计算 xxHash64，取低 20 bits。

验证结果：

- `cc_version`：如果按 cc2api 的“字节位置”算法验证，包含中文的 haiku 样本会不匹配；如果按 2.1.156 binary 中的 JS 字符串索引验证，haiku 样本 `b2a` 可以匹配。Opus 主会话样本仍不能用抓包 API body 首条 user 消息匹配，原因是 2.1.156 主会话使用内部 transcript，而不是最终 `/v1/messages` API body。
- `cch`：16 条带 billing 的 `/v1/messages` 全部不匹配。

这说明至少存在以下变化之一：

- `cc_version` 后缀输入源变了。
- `cch` hash 输入不再是完整 JSON body with placeholder。
- 序列化/canonicalization 不同。
- seed 或 hash 算法变了。
- `cch` 计算时间点在请求体构造过程的更早阶段，而抓包 body 已经过后续改写。

## binary 浅查结果

从 `@anthropic-ai/claude-code@2.1.156` 的 `claude.exe` 中用 `strings` 和 byte search 命中：

- `59cf53e54c78`：旧 salt 仍存在。
- `cch=00000`：占位符仍存在。
- `x-anthropic-billing-header: cc_version=`：billing 行模板仍存在。
- `xxHash64`：xxHash64 字符串存在。
- `Bun/1.3.14`：Bun UA 存在。
- `is_running_with_bun`：遥测 env 字段存在。

这说明“旧常量/模板仍在 binary 中”，但并不能说明 cc2api 旧实现仍正确。抓包复现失败更可信，优先判断为调用输入或 canonicalization 发生了变化。

## binary 深入定位

从 2.1.156 Linux x64 native binary 的打包 JS 片段中定位到以下逻辑：

```js
function ZLz(H) {
  let $ = H.find((K) => K.type === "user" && !K.isMeta);
  if (!$) return "";
  let q = $.message.content;
  if (typeof q === "string") return q;
  if (Array.isArray(q)) {
    let K = q.find((_) => _.type === "text");
    if (K && K.type === "text") return K.text;
  }
  return "";
}

function aKq(H, $) {
  let K = [4, 7, 20].map((A) => H[A] || "0").join("");
  let _ = `${WLz}${K}${$}`;
  return crypto.createHash("sha256").update(_).digest("hex").slice(0, 3);
}

function O69(H) {
  let $ = ZLz(H);
  return aKq($, VERSION);
}
```

主会话请求路径中调用顺序是：

```js
let R = O69(E);
system = [tr$(R), Q88(...), ...systemPromptParts].filter(Boolean);
```

side query 路径中另有：

```js
let G = cLz(messages);
let V = aKq(G, VERSION);
let v = tr$(V);
```

billing 行生成函数：

```js
function tr$(H) {
  if (CLAUDE_CODE_ATTRIBUTION_HEADER disabled) return "";
  let version = `${VERSION}.${H}`;
  let entrypoint = process.env.CLAUDE_CODE_ENTRYPOINT ?? "unknown";
  let cch = provider is not bedrock/anthropicAws/mantle ? " cch=00000;" : "";
  return `x-anthropic-billing-header: cc_version=${version}; cc_entrypoint=${entrypoint};${cch}${workload}`;
}
```

结论：

- `cc_version` 后缀算法在 2.1.156 中仍是 `salt + 字符串索引 [4,7,20] + version -> sha256 前 3 位`。
- cc2api 当前实现用 `as_bytes()[4,7,20]`，应改为 JS 字符串索引语义；中文、emoji 等非 ASCII prompt 会导致旧实现错误。
- 主会话的输入不是抓包最终 API body，而是归一化前的内部 transcript `E`。因此仅从 `/v1/messages` body 的首条 user 消息反算主会话后缀会失败。
- haiku side query 样本可以用抓包 API body 的首条 user 文本和 JS 字符串索引复现 `b2a`，这验证了公式本身没有变。
- Opus 主会话抓包中 `b94` 稳定，符合“首个内部非 meta user 消息在同一会话中固定”的行为。

## CCH 深入验证

已实现离线 xxHash64 验证，使用 seed `0x6E52736AC806831E` 对以下候选输入反算 16 条 billing 样本：

- 原始抓包 body 中把 `cch=<value>` 替换为 `cch=00000`。
- `JSON.stringify` compact 形式。
- ASCII escape compact 形式。
- key sort 形式。
- model 从 `claude-opus-4-8` 替换为 `claude-opus-4-8[1m]`。
- 移除 `metadata`。
- 仅 `system`。
- 仅 `messages`。

结果全部为 `0/16` 匹配。可以排除“cc2api 当前旧算法直接作用在 MITM 最终 JSON body 上”的解释。

### SEED 变更假设浅验

用户提出新的假设：`2.1.156` 的 CCH 可能仍使用旧 xxHash64 + placeholder body 方案，只是 seed 从 `0x6E52736AC806831E` 换成了新值。已做一轮不输出请求体的浅验：

- 从 `http_capture.jsonl` 正确抽取 16 条带 billing 的 `/v1/messages` 样本，统一把 `cch=<5hex>` 替换为 `cch=00000`。
- 旧 seed 在这 16 条样本上仍为 `0/16` 命中；前三条旧 seed 计算结果为 `595cb`、`4e3e8`、`ced69`，真实值为 `36de0`、`47eae`、`9df1f`。
- 在 `2.1.156` Linux ELF 中，旧 seed `0x6E52736AC806831E` 的 little-endian bytes、big-endian bytes、hex ASCII 和 decimal ASCII 都没有直接命中。
- binary 邻近字符串仍能看到 `WLz="59cf53e54c78"`、`cch=00000`、`x-anthropic-billing-header: cc_version=`，但替换 `cch=00000` 的函数仍未直接暴露在可见 JS 片段里。
- 使用旧输入模型验证候选 seed：旧 seed ±256、`59cf53e54c78` / `cch=00000` / `x-anthropic-billing-header` / `hashVersion` / `seed` / `2.1.156` 的若干 SHA256/BLAKE2 派生 seed，均无任何样本命中。
- 额外扫描 `0..2^20` 的小 seed 空间，未发现能同时匹配 16 条样本的 seed。

浅验结论：`seed 变了` 仍是合理方向，尤其旧 seed 在 binary 中不再直接可见；但“仅把 cc2api 旧算法的 seed 换成某个简单新 seed、输入仍是 MITM 最终 JSON body with placeholder”目前没有证据支持。下一步应优先定位 runtime/request 发送前的 CCH 替换点，或者用受控 hook 捕获替换前后的 body，再反推 seed 与输入。

### Linux 运行期 watchpoint 浅探

用户提供的 macOS arm64 逆向思路是：在 HTTP 请求被拦截时中断进程，扫描内存中的 `cch=00000`，对 5 个零设置写 watchpoint，从而定位 CCH 回填函数。已按同一思路在本机 Linux x64 `@anthropic-ai/claude-code@2.1.156` 上做受控复验：

- 本机 `claude --version` 为 `2.1.156 (Claude Code)`。
- 实际文件是 Linux x64 ELF：`/root/.nvm/versions/node/v22.21.1/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`，SHA256 与 `/tmp/claude-code-2.1.156.exe` 相同：`6d83cd2264450c5e54fc988be1032c288cf418ee604294acfb8fc4ac28f5f7a3`。
- 安装 `gdb` 后，用 `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`、dummy `ANTHROPIC_API_KEY`、`--bare`、`--no-session-persistence` 和本地最小 SSE 服务触发 `/v1/messages?beta=true`，不使用真实 token，不输出或落盘完整请求体。
- 本地 dummy 请求可稳定触发非零 CCH。示例安全摘要：body 长度约 `4135` 或 `4140`，billing 行形态为 `cc_version=2.1.156.492; cc_entrypoint=sdk-cli; cch=<5hex>;`。
- `sendto` 处读取发送 buffer 摘要时，HTTP 完整请求长度约 `4944`，billing 片段已经是非零 CCH；server 侧收到的 body 中也没有 `cch=00000`。
- 在 `connect` 时扫描匿名可写内存，可找到多个动态 `cch=00000` 副本；对其中 5 个零设置硬件 watchpoint 后，请求仍能发出且 watchpoint 不触发。
- 这说明 Linux/Bun 2.1.156 很可能不是把早期 heap 副本里的 `00000` 原地覆盖，而是在后续构造新的发送 buffer 时写入带非零 CCH 的 body。macOS 贴文中的“watch placeholder 原地写入”在 Linux x64 上不能直接复用。
- 对 `sendto` 抓调用栈，栈顶为 libc `send`，下一帧落在 Bun/native HTTP 代码地址附近；没有源码符号，暂未能直接命名 CCH 回填函数。
- 标准 xxHash64 prime 常量在 ELF `.text` 中大量存在，但对主要聚集函数地址设置断点后，本地 `/v1/messages` 请求期间未命中，说明 CCH 没有走这些可直接断下来的导出/普通 native xxHash64 入口，或相关逻辑发生在 JIT/内联/别的序列化路径里。

本地受控样本的离线验证：

- 对本地 dummy JSON body，把 `cch=<5hex>` 替换回 `cch=00000` 后，旧 seed `0x6E52736AC806831E` 仍不匹配。
- 对 raw TCP 捕获的完整 HTTP request bytes 做同样替换后，旧 seed 仍不匹配。
- 同 prompt 连续 fresh HOME 运行时，`cc_version` 后缀稳定为 `492`，但 body placeholder SHA 和 CCH 均变化。
- 固定 `--session-id` 且复用同一临时 HOME / `CLAUDE_CONFIG_DIR` 时，placeholder body SHA 和 CCH 都完全稳定。
- 固定 `--session-id` 后 fresh HOME 之间的 JSON 字段差异仅集中在 `metadata.user_id`、billing 行本身，以及一个 46 字符的系统块；这说明 CCH 更像确定性请求/body hash，而不是混入运行时随机 secret。

本轮结论：

- `2.1.156` 仍然先在 JS 层生成 `cch=00000` 占位符；这一点与 macOS 贴文一致。
- Linux x64 上 CCH 非零化不表现为对早期占位符 heap 副本的原地覆盖；应优先定位“最终 HTTP body / send buffer 构建”阶段。
- 旧 seed + 最终 JSON body、旧 seed + 完整 HTTP request bytes 都可排除。
- `seed 变了` 仍可能成立，但需要同时确认实际 hash 输入；目前不能只替换 cc2api 里的 seed。
- 下一轮应在 `sendto` 前的 Bun/native HTTP buffer 构建路径继续反查，或用 LD_PRELOAD/interpose `send`/`write` 的上游调用、JIT 符号日志、或更细的内存分配/拷贝 watchpoint 追踪最终 buffer 的来源。

### Linux body 源 buffer 分层定位

继续沿上轮 `send` buffer 往上追踪，已把非零 CCH 所在层级缩小到 HTTP request 对象的 JSON body 源 buffer：

- `send@plt` 的直接调用点在 `0x43c7248`，调用前 `rsi` 是完整 HTTP request bytes，`rdx` 是长度，示例长度 `4944`。
- `0x43c7150` 是 native socket send 包装函数；函数入口时 `rsi` 指向的完整 request 已含非零 CCH。
- 上游调用栈显示 `0x2e05926 -> 0x43c7150`。反汇编确认 `0x2e05400` 是 HTTP raw request 生成函数，负责把 headers 和 body 拼到发送 buffer。
- 在 `0x2e057d5`、`0x2e05805`、`0x2e05820`、`0x2e05920` 处读取请求对象字段：
  - `r14 + 0x4a0`：JSON body 源指针。
  - `r14 + 0x4a8`：JSON body 剩余长度。
  - `r14 + 0x4d8`：已发送/偏移计数。
- 在 raw request 生成函数刚完成 headers 后，`r14+0x4a0` 指向的 JSON body 源 buffer 已经包含非零 CCH；示例安全摘要：body 长度 `4135`，billing 片段为 `cc_version=2.1.156.492; cc_entrypoint=sdk-cli; cch=<5hex>;`。
- 对 JSON body 源 buffer 的 `cch` 五位 hex 打写 watchpoint，后续不会触发；说明进入 `0x2e05400` 前 body 已经成型，HTTP raw 拼接层只读/复制它。
- 在该时刻扫描同一非零 CCH 的明显内存副本，没有找到其他含 billing/JSON 上下文的动态副本；最终连续 body 可能只存在于 HTTP request 对象中。
- 因此下一轮真正有价值的断点不是 `send`、`sendto`、`0x43c7150` 或 `0x2e05400`，而是 request 对象字段 `0x4a0/0x4a8` 被填入之前的 fetch/body 构造路径。

### Linux CCH 替换点和 seed 最终定位

继续用本地 dummy 服务和 dummy API key 做运行期断点复核后，修正了上轮对 raw HTTP 层的判断：

- 在 `0x2e05400` 入口，带 billing 的 `/v1/messages` body 源 buffer 仍然是 `cch=00000`，不是非零 CCH。
- `0x2e05400` 内部会调用 `0x2e05b10` 生成 header/body 片段；该函数先搜索 `/v1/messages`，再在 body 中搜索 `cch=00000`。
- 命中占位符后，函数会初始化标准 `XXH64` 状态并对整个 JSON body（保持 `cch=00000`）做 hash。
- `state+0x20` 的 seed 为 `0x4D659218E32A3268`；这会推导出初始化向量：
  - `seed + PRIME64_1 + PRIME64_2 = 0xAE4FBA0790EAE83E`
  - `seed + PRIME64_2 = 0x101840560AFF1DB7`
  - `seed = 0x4D659218E32A3268`
  - `seed - PRIME64_1 = 0xAF2E18675D3E67E1`
- hash finalize 后取低 20 bits，编码为 5 位 hex，写回 `cch=` 后面的 5 个字节。写回点在 `0x2e06878` / `0x2e0687e` 附近。
- 本地内存校验中，`xxhash.xxh64(body_with_cch_00000, seed=0x4D659218E32A3268) & 0xFFFFF` 与进程内 finalize 结果一致。
- 对抓包 run `46ba25a8d791` 的 16 条带 billing `/v1/messages`，将 `request.body_text` 第一处 `cch=<5hex>` 替换为 `cch=00000` 后，用该 seed 计算，结果 `16/16` 匹配真实 CCH。前三条安全摘要：
  - body 长度 `2214`：真实 `36de0`，计算 `36de0`
  - body 长度 `54672`：真实 `47eae`，计算 `47eae`
  - body 长度 `69346`：真实 `9df1f`，计算 `9df1f`

最终结论：

- Claude Code `2.1.156` 的 CCH 算法仍是 `XXH64(body_with_placeholder, seed) & 0xFFFFF`，输入就是最终 JSON body 中把 CCH 保持为 `00000` 的字节序列。
- 与旧版本的差异是 seed 从 `0x6E52736AC806831E` 变为 `0x4D659218E32A3268`，并且 Linux x64 的替换发生在 native HTTP 发送路径中，而不是可见 JS 片段里。
- cc2api 可以安全恢复 `2.1.156` 的 CCH rewrite，但必须按版本选择 seed；旧版本保留旧 seed。

本轮额外候选输入排除：

- 固定 `--session-id`、dummy key、dummy `ANTHROPIC_BASE_URL` 的受控 body，继续用旧 seed 验证以下输入，均不匹配真实 CCH：
  - body 中将 `cch=<5hex>` 替换回 `cch=00000`。
  - 含真实 CCH 的 body。
  - compact JSON placeholder。
  - key sort compact JSON placeholder。
  - 仅 `metadata`、仅 `system`、仅 `messages`、仅 `tools`。
  - 删除 `metadata`、删除 `metadata.user_id`、删除若干 system block 后的 body。
- 该结果进一步排除“旧 seed + 这些常见 body 子集/规范化输入”的解释。

telemetry 进一步证明：

- `tengu_sysprompt_block.hash` 对应的是占位符 billing 行。
- `cc_version=2.1.156.b94; ... cch=00000;` 的 SHA256 前缀是 `627d51f1ed88`，与 telemetry 中主会话 sysprompt block hash 一致。
- `cc_version=2.1.156.b2a; ... cch=00000;` 的 SHA256 前缀是 `6f52bf86e045`，与 haiku side query telemetry 一致。

因此 CCH 替换发生在 system prompt 组装和 telemetry 上报之后、最终 HTTP 请求发出之前。当前 binary 可见的 JS 片段没有直接暴露 `cch=00000` 的替换函数；`xxHash64` 字符串更像 Bun/JavaScriptCore runtime 内部符号，不能证明应用层直接调用 xxHash64。

目前最强判断：

- `cch=00000` 是应用层先写入 system prompt 的占位符。
- 真正的 5 位 `cch` 由 native HTTP 发送路径在请求发出前计算并写回。
- 输入是 MITM 看到的最终 JSON body，把真实 CCH 替换回 `00000` 后的字节序列。
- Claude Code `2.1.156` 可以按新 seed 复现 CCH；旧 seed 仅适用于旧版本。

## 当前假设

1. `cc_version` 后缀算法未变，但输入源和索引语义需要修正：主会话用内部 transcript 首个非 meta user 消息；side query 用 API messages 首个 user 文本；索引按 JS 字符串索引，不按 UTF-8 字节。
2. `b94` 在同一 Opus 会话稳定，说明内部 transcript 的首个非 meta user 消息稳定。
3. `cch` 随请求增长变化，本质是请求 JSON body hash；`2.1.156` seed 为 `0x4D659218E32A3268`。
4. `cch` 仍为 5 位 hex，binary 仍含 `cch=00000`，运行期替换点证明应用层发送路径使用标准 XXH64。

## 下一步研究矩阵

- 生成更多 controlled capture：
  - 同版本、同 model、同 prompt 连续多次。
  - 同版本、不同 model。
  - 同 model、极短 prompt / 长 prompt。
  - 同一会话首轮与多轮。
- 后续如升级到新 Claude Code 版本，优先在 binary 中搜索 `cch=00000` 和 `XXH64` 初始化向量，确认 seed 是否再次变化。
- 离线回归应固定为：最终 JSON body 中真实 `cch=<5hex>` 替换回 `cch=00000`，再按版本 seed 计算。
- 运行期 hook：
  - 使用 `--debug` / `CLAUDE_CODE_DEBUG_LOG_LEVEL=verbose` 查看是否能输出 `[API REQUEST DETAIL]` 或 attribution header，但不要输出 token。
  - 用本机 2.1.156 加受控 prompt，捕获 side query 与主会话各至少 3 条。
  - 若允许更深入，可用 LD_PRELOAD/undici fetch hook 观察请求发出前 body 与 MITM body 是否一致，但必须避免落盘 token 和完整 prompt。

## 对 cc2api 的实现建议

- `2.1.156`：`cc_version` 后缀按 JS 字符串索引语义计算，CCH 使用 seed `0x4D659218E32A3268`。
- 旧版本：CCH 继续使用 seed `0x6E52736AC806831E`，避免影响既有行为。
- API 注入模式和真实 Claude Code 客户端模式都可以在 `billing_mode=rewrite` 下重置为 `cch=00000` 后按版本 seed 回填。
- 继续禁止提交抓包原文、OAuth token、prompt、响应正文或账号 profile；测试 fixture 使用最小 JSON 或安全摘要即可。
