# 实施计划：SSE 事件与压缩长流统计

## 前置与开工边界

- [x] 用户已选择 R4-01／02，创建规划任务；冻结第四轮记录保持只读。
- [x] 已核实 UsageCapture、AttemptTrace、SlotGuardBody、缓冲入口及现有模型／存储签名，记录事件与生命周期研究。
- [x] 增量 codec 研究收口：39 行离线观测断言通过，明确有限 deflate 分流与四层窗口工作区边界；这些探针不代替产品验收。
- [x] implement.jsonl／check.jsonl 各配置 8 条真实规范／研究上下文，task.py validate 通过。
- [x] 完整 Brief 已展示，用户回复“确认”；2026-10-29 已执行 task.py start，进入实施。
- [x] 已按 trellis-route 的真实结果实施，并完成 trellis-before-dev、目标定义及规范核实。

## 执行顺序

### 1. 统一有界事件观察

- [x] 在 usage.rs 把单 data 行解析替换为完整 SSE 事件状态，支持多 data、三种换行、跨块 CRLF／BOM、注释及空块。
- [x] 完整 JSON 与单行／单事件保留 1 MiB 上限；超大事件跳至下个空行再同步，EOF 未派发事件不消费。
- [x] 复用既有 observe_value／累计 max／真实零／缓存 TTL 明细／模型与 speed／部分费用规则。
- [x] 增加真实结果断言：相同流各种排版／chunk 得到一致六类 token、模型、停止原因和 partial；未知事件不误报，缺空行不提前计入尾部用量。

### 2. 有界增量 codec

- [x] 新增内部 response_body_codec.rs，沿用已有依赖，核实研究中实际接口；禁止整条输入／中间输出 Vec 聚合。
- [x] gzip／x-gzip 多 member、zlib／raw-deflate、strict br、zstd 多 frame／skippable，逆序编码链；最多 4 有效层，标准 br 和 zstd 的窗口边界按设计执行。
- [x] 持久下游 sink 直接进入下一层／末端事件状态；固定小输出块、进度检查和显式 finish；故障后保留已有摘要并停用故障观察。
- [x] 验证 deflate 普通两种格式，明确 zlib 头碰撞的保守 partial；不得暗中承诺整包 fallback 完全等价。
- [x] 验证 CRC／checksum、截断、尾随输入、第二 member／frame 错误、窗口与层数超限。正常结束与异常 Drop 都不触发重复完成。

### 3. 接入所有既有入口

- [x] UsageCapture 统一配置／feed／finish，已有 observe_encoded 一次性入口委托同一机制。
- [x] AttemptTrace 在 headers 配置、每块 observe，不再积累整条压缩副本；保留同步终态、根／尝试顺序和安全计数。
- [x] SlotGuardBody 对所有编码逐块观察，finish 不再从 stateful side tap 解整包；保留原 stateful／telemetry 用途和生命周期。
- [x] 核对正式非流探针及诊断既有缓冲响应，不能漏采或重复观察；cache hit 仍零新增正式调用记录。

### 4. 真实转发验证

- [x] 扩展 Gateway 本地上游与 SQLite／DiagnosticsStore 测试，涵盖 API／CC、JSON／SSE、编码链、正常／取消／body error。
- [x] 两类长 SSE：低熵内容令 decoded >1 MiB，以及合成噪声令 compressed raw >1 MiB；每个事件长度正常，头尾 usage 在所有目标 codec 可观察。
- [x] 客户端字节逐字节等于上游、状态与有效编码头保持匹配；每次实际成功调用只落一条用量，诊断一条实际 attempt，不新增请求。
- [x] 取消发生在已输出首个 usage、未收 footer／结束事件时，部分 token 可用、partial 明确，原取消和传输错误向下游正常表现。
- [x] 超大 JSON／行／事件、未知编码、损坏／截断、缺结束帧／尾空行，保持受控采集故障和既有费用语义；安全摘要无合成秘密文本。
- [x] 用结构内存计数／缓冲长度断言证明不保留整条响应；资源结论区分工作区估算与实测，不用一次 RSS 值声称硬上限。

## 验证命令与证据

以下命令在 cc2api 目录执行；新增测试名称落地后同步精确过滤器与结果，不把未运行的计划当作通过。

```bash
cargo fmt --check
cargo test service::usage::tests
cargo test service::response_body_codec::tests
cargo test service::diagnostics::tests
cargo test gateway_usage
cargo test gateway_compressed_request
cargo test keepalive
cargo test cch
cargo test
```

- [x] 逐项记录命令、退出码、passed／ignored 与日志路径；若已有 PostgreSQL 环境相关忽略，说明真实原因，不伪称已覆盖 PostgreSQL。
- [x] 有效窗口／chain、真实零与 cache 分项、观察故障计数、根终态不可被迟到快照覆盖，需要实际行为断言，不只镜像实现。
- [x] 测试通过后不无依据重复昂贵全量；新变更／失败或尚未覆盖的问题才触发补跑。
- [x] 父仓与子仓精确范围 whitespace 检查通过，冻结 round4 与无关工作不变，产品 diff 仅包含授权范围。

## 评审、规范与交接

- [x] 实现完成后按 trellis-route(target=check) 进入 Check-All，由其选择深度；既有检查修复遵从当前报告，不重建规划任务。
- [x] 评审重点：Writer sink 不积累整包、所有层严格结束、frame／头不变、一次性收口、未知不等于零、诊断错误分类、deflate 兼容例外与极端工作区。
- [x] 检查通过后评估并更新 settings-database.md 中“整个压缩响应 1 MiB”的过时合同，记录每 JSON／行／事件与 codec 资源边界；不把本轮改成设置／数据库项目。
- [x] 已按确认的精确 Git 计划提交并推送业务代码与规范，任务记录随本次完成态收口；没有部署。

## 风险文件与回滚点

- usage.rs 影响用量与诊断；先跑共享解析结果与价格回归，再接 Gateway。
- diagnostics.rs 的同步 finish 影响根终态；不把它改成异步迟到摘要。
- gateway.rs 只改正式用量接线与相关测试；stateful／telemetry、保活、请求 codec、CCH 及重试路径作为回归边界。
- 新模块可以随上述接线一并回退，无迁移和历史费用回算；不得回退其它任务或用户已有变更。

## 本轮实施与验证证据

- 产品范围：usage.rs、response_body_codec.rs（新增）、diagnostics.rs、gateway.rs、service/mod.rs；原累计合并逻辑保持原字节。
- 定向测试：8 个 UsageCapture 测试通过（/tmp/cc2api-r4-usage-expanded.log），7 个 codec 测试通过（/tmp/cc2api-r4-codecs.log）；末次 Drop 保护已由最终全量再次覆盖。
- Gateway 5 个定向测试通过（/tmp/cc2api-r4-gateway.log）：新增 72 个小响应组合、32 个长流组合、4 个取消／读错组合及故障样例；两种客户端原始响应一致，用量与诊断匹配。
- 缺结束帧追加后故障测试再次通过（/tmp/cc2api-r4-failures-final.log）；5 个诊断测试通过，含新增压缩缓冲分支（/tmp/cc2api-r4-diagnostics-final.log）。
- 未修改 R3-01／R4-03／R4-04、请求 codec／CCH、stateful 缓存或自动遥测规则；未提交、推送或部署。

- 最终 cargo test（/tmp/cc2api-r4-full-final.log）：退出 0，761 passed／0 failed／3 ignored；三项既有 PostgreSQL 专项需独立测试 DSN，本次未改 SQL／迁移。
- 同一全量包含 CCH 40、压缩请求 Gateway 12、keepalive 4、codec 7、UsageCapture 8、诊断 5、Gateway 用量 5 个通过测试；复用覆盖关系，不再重复运行相同过滤器。
- cargo fmt --check 退出 0（/tmp/cc2api-r4-fmt-final.log）；已跟踪与新增 codec 的空白校验通过。新增文件 no-index diff 的原始退出 1 表示文件存在差异，stdout／stderr 为空，不是空白错误。
- 范围检查：父子仓 HEAD 不变，子仓只改 5 个授权 Rust 文件，337 个原有未跟踪文件及原跟踪修改保持，全部 13 个冻结 R4 文件 SHA256 一致。
- Check-All：auto→full，三件套／实现假设／完整性与规范均通过；CHK 0／FBK 0；DOC-001 机械同步本实施记录，不改需求／设计／Brief。后续按 owner 进入 Spec 更新与精确 Git 计划评审。

- 按诊断规范补充 cargo test --locked（/tmp/cc2api-r4-full-locked-final.log）：退出 0，761 passed／0 failed／3 项既有 PostgreSQL ignored；Cargo.lock 未改。
- Update-Spec 返回 written：仅 .trellis/spec/cc2api/backend/settings-database.md 改动，新增六节有界响应观察合同，锚点／签名／测试符号及空白检查通过；本轮其它源文件和任务外资料不变。
- Push 计划已获用户确认；两个业务仓库已提交并推送，当前任务的完成态与关闭记录由 task_progress.py write --complete 一次写入。
