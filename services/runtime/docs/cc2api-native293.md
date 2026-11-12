# cc2api 原生 293 转发

Linux x64 分发文件为 `ccrb-runtime-linux-x64`，实际大小 **27387960 字节（26.12 MiB）**。它是内含固定官方 2.1.293 构造和发送逻辑的执行内核。cc2api 提供账号管理、鉴权、调度、凭据刷新和用量记录。

## 运行与身份

运行环境需要 Linux x64、glibc、`/proc`、可执行的 memfd 和独立可写 HOME/config/cwd。初始化需要可写 `/tmp`。Python、Bun、官方 CLI 源文件、解压目录及构建工具属于构建或验收侧依赖。

| 身份 | SHA256 |
| --- | --- |
| 官方来源 2.1.293 | `8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978` |
| 分发文件 | `423a6a848c84e09bcc73a8b7be481ed4ead44a6644cef94bbf47d2009d3f6b80` |
| memfd 执行体（112839864 字节） | `22f26d7803f80630968caf21b6170cf9bb94d87bea6f5eef678464f3bb0d3ecd` |

当前发布线为 `v0.1.0-beta.3`，入口删除顶层 `settings`、`claude_settings`、`env` 后继续处理，业务嵌套字段保持。

两次独立构建得到相同分发字节及执行体。加载器校验展开载荷并封存 memfd；消费者通过已校验文件 FD 启动，核对就绪 PID、版本、能力及 `/proc/<pid>/exe`。

## 按账号接入

1. 在同一批 V3 镜像中加入新 cc2api 消费者及原生二进制。bench 构建从固定 beta 附件获取文件，并校验上述 SHA256。发布前可用 `V3_NATIVE_RUNTIME_ASSET=/绝对路径/ccrb-runtime` 指定同校验值的本地候选。
2. 显式设置 `V3_NATIVE_SENDER_MEMORY`，并保证已冻结的账号 RAM 总预算足够。账号标准并发 3 需要覆盖 6 个 Haiku 物理进程，预检最低为 `1408m`，已验证的部署配置使用 `1536m`。例如账号总 RAM 为 `4g` 时，network 保留 256 MiB，原生 sender 1536 MiB，CLI 2304 MiB。额外 swap 只属于 CLI。
3. 在 cc2api 账号创建或编辑中选择“原生运行时 2.1.293”，对应 `request_backend=native293`。历史账号和省略值为 `legacy`。后端切换要求账号空闲；sender 布局变化会在账号环境无活动作业时重建角色实例。
4. `POST /v1/messages` 在 Rust 协议改写之前交给二进制。普通 Messages API 与完整原生 293 输入沿各自构造合同处理。白名单过滤调用方头，运行时生成自身身份、上下文和 CCH。
5. 原生模型请求保持单次提交。上游错误返回本次调用方。账号空闲时选择“原有转发”可恢复 `legacy`。

首版使用 V3 账号 sender。原生进程只取得当前 bearer、设备和账号身份。refresh token 由网关持有。缺二进制、能力、资源或身份校验失败时返回准备错误。其余端点继续走现有发送方式。

共享池预算公式为 `256 + 192 × 2 × 标准并发` MiB。bench 的账号创建流程默认标准并发 4，对应最低 1792 MiB sender 预算；也可将该账号标准并发显式设为 3，使用已实测的 1536 MiB 配置。更高并发按公式及账号总 RAM 校验，满载资源仍需在部署环境实测。

## 共享映像与空闲回收

首个进程的实际执行映像经过长度、SHA256及四项封存核验后，由本账号池持有只读FD。后续进程从同一映像重新exec，并核对实际dev/inode；每个进程保留独立堆、SDK、HOME/config/cwd和作业根。额外进程空闲60秒后回收，保留一个暖进程，下一批请求按账号并发额度扩容。

## 私有协议

启动时设置 `CCRB_WORKER_ID`，使用私有 stdin/stdout JSONL。握手为 schema 2 `worker_ready`，并声明 `raw_input_protocol:1`。请求示例：

```json
{"type":"request_input","schema_version":2,"worker_id":"11111111-1111-4111-8111-111111111111","request_id":"request-001","input":{"schema_version":1,"request_id":"request-001","body":{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"测试"}]},"headers":[],"context":{}}}
```

二进制依次返回实际 `header_policy` 决策、`cc_prepared` 组装快照、响应头、base64 响应片段、唯一终态和匹配 `worker_idle`。组装快照是原生封口前值。只有终态及 idle 收齐后才复用进程。取消和通道错误退役进程，下一请求按需重建。

error 事件可选携带 `diagnostics`，版本为 1。`stage` 标记实际 input、context、construction、dispatch、response_headers 或 response_body 边界；未知时为 unknown。`causes` 最多八项，只包含受控 `name/code`，并通过 `chain_truncated/cycle_detected/inspection_failed` 标记边界。白名单由 `src/shared/native-error-diagnostics.ts` 所有，TypeScript 与 Rust 共用夹具核对目录。异常 message、stack、URL 和扩展属性不进入摘要。

TypeScript 解码器先验证业务错误及请求归属，再重建 error 载荷。非法或未知版本摘要被移除，并附加 `diagnostics_state="invalid"`；原 code/status 保持。worker 帧的消费者接收规范化后的载荷。旧事件省略该字段，Rust 也识别规范化失效标记。

平台 sender 默认将结构化 JSON 日志写入标准输出，支持 `RUST_LOG`。`native_error_event` 日志包含 job/attempt、worker/PID、账号、环境代次，以及 `diagnostics_state`、`error_stage` 和安全摘要。网关提交日志提供根 request_id 到 job 的关联。旧内核缺省摘要时标为 unavailable，Rust 消费端拒绝畸形摘要并标为 invalid，保持原业务响应。worker 的 stdout 继续只承载私有协议。

完整 cause 采集依赖已构建并接纳相应源码的内核制品；只更新平台 sender 时可以恢复既有日志及缺省状态。固定制品身份、签名接纳与 TLS 探针准入沿原发行流程。

## 离线验收

```bash
# 真实 Rust 消费者、V3 内部 HTTP 和独立 TLS 上游
CCRB_TEST_CC2API=/绝对路径/cc2api \
CCRB_TEST_BINARY=/绝对路径/ccrb-runtime \
bun scripts/testing/cc2api-native.ts

# 干净固定镜像：独立二进制、无外网、有限 RAM
python3 scripts/testing/standalone-native.py \
  --binary /绝对路径/ccrb-runtime --output /新的验证目录
```

当前共享池在真实V3三角色、两账号、HTTP/SOCKS离线TLS场景中，分别完成3路普通和6路Haiku请求；29组场景全部通过。sender上限为1536 MiB，HTTP峰值676216832 B（约645 MiB），SOCKS峰值677347328 B（约646 MiB），OOM计数均为0。60秒空闲回收后，一个暖进程的sender占用为198385664 B（约189 MiB）。这些数字来自合成短请求，实际请求体量会影响堆和缓冲占用。

早期独立映像的干净Python夹具完成9次TLS实收，2432 MiB上限内峰值1631354880 B，包含TLS夹具和校验器。该批次记录保留在任务验收文件。运行时内存展开与分发文件体积分别统计。

beta.3 的最终二进制重新通过 67 项原生回归、HTTP/SOCKS 各 19 次消费者 TLS 实收与 6 路并发验证；消费者 Rust 单测 766 项通过。两次独立构建的分发及执行体摘要一致，24 项构建源码摘要与来源提交逐项匹配。

独立 Python 容器以单文件启动 3 路普通和 6 路 Haiku 请求，共 9 次 TLS 实收；每次原始私有请求均携带三个顶层本机设置字段，实收正文确认已移除。整个验证容器峰值为 1629663232 B，OOM 计数为 0；该峰值包含 TLS 夹具与校验器。

## 内核在线分发附件

一次性支持在线升级的 V3 底座可按账号准备、激活和回滚固定 293 的后续内核修订。镜像内置 beta.3 的登记继续保留。发布时先按本页离线验收验证最终分发 SHA256 和实际执行体，再在发布端使用专用 Ed25519 私钥生成三个同批附件：

```bash
bun scripts/seal-runtime-release.ts v0.1.0-beta.4 /绝对路径/ccrb-runtime-linux-x64 /发布端/ed25519.pem /全新输出目录
```

工具读取分发文件旁的构建清单。输出 `runtime-release.json`、64 字节原始签名 `runtime-release.sig` 和 `ccrb-runtime-linux-x64`。部署端以预先登记的公钥核对原始清单字节，独立核对分发 SHA256；sender 在真实 worker 握手后从进程映像读取并核对 SHA256 及四项封存。签署动作代表发布者批准最终制品；构建或签署命令成功本身不替代离线验证。
