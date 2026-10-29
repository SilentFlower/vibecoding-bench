# 压缩请求实施计划

## 实施前门槛

- [x] 用户明确兼容合法压缩输入、改写后按原编码出站、使用子 agent。
- [x] 已检查两个入口、全部发送／signature 重试、CCH／Session／缓存及 runtime 字节／长度边界。
- [x] 依赖的实际编解码 API、严格结束、窗口和容器膨胀已研究，官方 300 gzip 证据落盘。
- [x] 收敛 PRD 并配置真实 implement／check jsonl 上下文。
- [x] 已完整展示 Brief；用户回复“确认开始吧”，首次开工批准成立。
- [x] 已运行 `task.py start`，状态为 in_progress；路由确认 subagent，复用用户选择。

## 所有权与执行顺序

Gateway 实施 agent 负责 `cc2api/src/service/mod.rs`、`service/gateway.rs`、实际 Gateway 集成测试与本任务 `validation.md`／本计划进度；独立 codec 实施 agent 仅负责新 `cc2api/src/service/request_body_codec.rs` 及其内置单测。主会话负责规划、研究上下文和后续交接。双方不是唯一工作者，不撤销其它已有改动；先读取实际类型和函数定义，再写中文注释及 API 文档。最终格式、全量与 CCH 验证由 Gateway agent 汇总执行，codec agent 只运行模块定向检查。

共享接口固定为 `REQUEST_BODY_LIMIT`、`RequestBodyEncoding::{from_headers,is_encoded,content_encoding,decode,encode}` 与五个无字段 `RequestBodyCodecError` 变体 `InvalidEncoding`／`UnsupportedEncoding`／`TooLarge`／`InvalidBody`／`Internal`。无有效编码的 `decode` 原样保留 `Bytes`，`encode` 返回 `Cow::Borrowed`；有效编解码使用 blocking worker。Gateway 负责原字节读体错误分类、HTTP 映射以及发送前 CE／CL／TE 清理。接口调整先由双方及主会话协调。

1. [x] 基线指纹已保存至 research/execution-baseline.json，子仓干净；冻结差分研究只读。
2. [x] 先加实际 Gateway 的失败回归：收到 gzip 后，上游应收到可解码的最终正确正文及一致编码头；在基线运行证明能发现原缺陷。证据见 `validation.md`。
3. [x] 实现共享编码计划及严格有界解码，覆盖现有 codec 的完整结束、输入耗尽、每层大小与窗口；明确错误分类，由 Gateway 映射 Anthropic error。
4. [x] 两个入口接线，保留鉴权／方法优先级及无编码路径；解码早于正文策略和账号副作用，通用转发保留 JSON／非 JSON 语义。
5. [x] 普通发送、count_tokens、signature 重试传入冻结编码选择；CCH／缓存／诊断继续使用逻辑正文，网络前正序编码并清除旧传输头。不新增重试或 bridge 字段。
6. [x] 完成验证矩阵，运行格式、全量与 CCH 检查；在 validation.md 记录命令、退出码、覆盖／缺口和文件指纹，更新本计划完成项。最终全量 745 passed／0 failed／3 既有 ignored；CCH 40 项通过。
7. [x] 主会话独立 Check-All 完整审查通过，CHK／FBK／DOC 均为零；已同步后端请求编解码规范并核对仅 Spec 文件变化。进入精确 Push 计划评审，未经该阶段确认不提交／推送。

## 验证矩阵

| 层级 | 必须覆盖 |
| --- | --- |
| codec | gzip／x-gzip、zlib／raw-deflate、标准 br、zstd 往返及顺逆序；CRC／ISIZE／Adler／可选 checksum、截断、尾随输入、多 member／frame、skippable frame；窗口、层数和片段边界。 |
| 大小 | 原字节、各层输出的恰好 10 MiB／加 1／中间层超限；到达 limit 仍做结束校验；近 10 MiB 合法正文重编码容器膨胀仍可发送。 |
| Gateway＋TCP | CC／API；Messages、count_tokens、event_logging、通用非 JSON 路径；重复头／大小写／OWS／identity／空列表／叠加。实际 CE／CL 与 wire bytes 一致，解码后验证身份、Session、CCH、根键清理和 stream 三态。 |
| 本地结果 | 未知 415、非法／截断等 400、压缩超限 413，可解析错误；拒绝先于账号／RPM／slot／池／Hello／遥测，业务上游为零；鉴权／方法优先级及 warmup／prefill／classifier／缓存命中等价。 |
| 重试 | 本地上游触发 401、两阶段 signature 400、429 换号，每次发送本次正确逻辑正文及 CCH，编码不漂移，不新增额外重试。 |
| 原行为 | 无编码、只有 Accept-Encoding、identity／空声明；未压缩读体错误和各端点非法 JSON 语义；R2 字段开关／普通 Session／探针／池、beta/query、stream 和 CCH 回归。 |
| transport | 直连真实 TCP 长度；v3 bytes／PreparedRequest 合同断言或既有对应测试，不改协议、不启动生产环境补测试。 |

定向测试按实际新增名称运行并记录，不能预先把未定义名字写成已通过命令。实施至少执行：

```bash
cd cc2api
cargo fmt --check
cargo test --locked
cargo test --locked cch
git diff --check
```

本项不改前端，不重复前端构建。standalone probe 不能代替实际 Gateway 验收；合成上游不能冒充新抓包或真实推理。全量通过后不无故重跑，后续新变更／失败再补相应检查。

## 风险与回退点

- 严格解码、层数、窗口和中间大小是有限支持边界，不声称任意合法流皆可用。
- 解压／重压缩增加 CPU 和内存；这些上限不是总内存或可取消 CPU 超时保证。使用普通固定参数及 blocking worker，不增加全局调度框架。
- 响应 R3-01、响应解码、TLS／新画像维持本项之外，发现独立缺陷只记录。
- 回退只撤销本项对应 diff，保留其它任务及父仓文档；扩大产品范围前先同步材料、解决新决定。
