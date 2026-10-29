# 当前源码核对

核对日期：2026-10-28。用户最终选择“每次抓包独立版本 + 提前停止后保留数据”，不要求原进程续跑。本文件是规划依据，不代表功能已实施或真实采集验收已完成。

## 已有能力与缺口

| 入口 | 当前事实 | 本轮规划影响 |
| --- | --- | --- |
| `orchestrator/main.py:11024`，`CaptureRunIn` | 有账号、题目、模型、effort、权限和超时，无版本输入 | 新增可选的单次抓包版本字段 |
| `orchestrator/main.py:11386`，`start_capture_run` | 从全局有效版本取值，已写入 runs.claude_code_version 并传给调度器 | 复用字段，改为“显式版本优先、留空沿用全局” |
| `orchestrator/main.py:1962` | 已有版本规范化与 run 快照解析函数 | 复用校验，避免另造版本规则 |
| `orchestrator/account_runtime.py:768` 与 `images/account/cli-version.sh` | 按精确版本准备 `/cli/<version>`，检查 CLI 实际版本并标记 ready | 独立版本不需要单独镜像；安装失败不能静默回退 |
| `images/v3/Dockerfile` 与 `.github/workflows/v3-build.yml` | 同批 control/account 镜像；账号 CLI 通过版本缓存准备 | 本轮默认不改镜像拆分或构建发布流程 |
| `images/sidecar/recorder.py:362` | 每条完成 flow 后原子更新轻量索引，原始 JSONL 追加写入 | 已有运行中查看基础；补数据完整性与停止收尾验证 |
| `images/sidecar/recorder.py:738` | 完整记录主要由 response 回调写入 | 未完成响应必须区别于完整 flow；不能许诺尚未落盘的内容已保存 |
| `orchestrator/main.py:11853`，`get_capture` | 不要求 run 终态，聚合分代索引并列出原目录文件 | 增强运行中/提前停止后的反馈，兼容旧平铺与分代目录 |
| `webui/app.js:2451` | 详情运行中刷新抓包信息 | 复用现有机制，不新增另一套轮询 |
| `orchestrator/main.py:11926` 与 `orchestrator/account_runtime.py:1812` | 停止按当前代次认领，清理 driver 与网络上下文后写 stopped | 首版复用停止，不扩展可恢复暂停状态机 |
| `images/account/network-context.py:54` | 旧监听先 SIGTERM，约 2 秒后可能 SIGKILL | 增加 Recorder 收尾和强制退出后的已落盘数据保留验收 |

## 核查时避免误判

- “已有运行中索引”不等于每条响应都已经完整落盘；流式响应仍可能处于进行中。
- “停止执行”不等于删除 run、workspace 或 flows；数据保留必须分别验证索引、原始 JSONL、stats 与 .flow。
- 没有完整索引时仍可能存在 .flow 或 stats，页面不能只根据 available=false 宣称没有抓包数据。
- 新 run、重试和历史续聊的执行目录必须保持隔离；读端继续聚合，写端不能复用旧文件并覆盖历史。
- 现有终态续聊入口只接受已结束 run，和用户原先提及的可恢复暂停不同；它不属于本轮新增目标。

## 关联规范与研究

- [正式抓包契约](../../../../.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md)：API 身份、代理链路、完整记录、索引与证据边界。
- [V3 运行契约](../../../../.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md)：版本缓存、独立 CLI 调度、网络上下文及执行代次；该文件较大，后续按 60-95、180-205 等实际章节定向读取，不能依赖截断的上下文注入。
- [WebUI 质量约束](../../../../.trellis/spec/vibecoding-bench/frontend/quality-guidelines.md)：零构建、escapeHTML、模态关闭与长连释放。
- [303 TLS 与正文研究任务](../../10-28-cc2api-303-tls-body-alignment/prd.md)：本次抓包升级为后续研究提供工具能力，不自动执行该研究或升级协议画像。
