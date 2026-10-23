# 真实项目审查：Boltons

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[mahmoud/boltons](https://github.com/mahmoud/boltons)。标准库扩展工具集，真实模块覆盖文件、流、URL、缓存、统计、日期、函数包装和嵌套数据处理。
- 固定提交：[4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d](https://github.com/mahmoud/boltons/tree/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d)；版本与运行要求：26.2.1dev，Python >=3.7。
- 许可证：BSD-3-Clause。保留 LICENSE 的版权、三个条件和免责声明；不能用贡献者姓名暗示背书。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 113 个，985,171 字节 |
| Python 产品源码 | 30 个文件、17,396 行 |
| Python 测试文件 | 31 个、6,518 行 |
| 隔离依赖安装 | 11.492 秒，venv 52,480,336 字节 |
| 适用原生基线 | 678 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 6.893 秒，峰值子进程 RSS 191732 KiB |
| 容器运行 | 整体 7.491 秒，内存 256 MiB、PID 64，无 OOM |

产品没有第三方运行依赖。研究预备 pytest、python-dateutil、attrs、pytz；精确版本见冻结清单。无需独立服务或云账号。首次无代理的依赖下载超时已保留；使用本机无认证代理重新准备成功，运行阶段离线。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Boltons 是多个可独立使用的真实模块而非单一 Web 应用。原生源码中的 AtomicSaver 有文件 fsync 和原子 rename；JSONLIterator 有正反向与忽略坏行；SpooledStringIO 用 UTF-8 字节流维护字符位置；funcutils 动态构建函数签名；LRU 使用双向链表；Stats 缓存统计结果。本轮读取上述定义、公开签名及现有 tests/doctests，路线围绕这些既有能力演进。

使用 atomic_save 真正写出临时 JSONL 文件，JSONLIterator 读回，remap 删除嵌套 None 后核对业务数据。独立复现 6 类缺陷：文本流 rollover、tzinfo 判定、regex flags、falsey key、排序 key 重算、仅限位置参数签名。另观察显示舍入和月底跨月两项需要显式兼容策略的增强，不混称缺陷。

## 基线范围与限制

按上游 tox 的 pytest --doctest-modules 思路运行整个 boltons 与 tests：678 项主测试／doctest通过，另 12 个 subtests 通过，0 失败／错误／跳过。JUnit 的 tests=690 包括子测试，与终端 678+12 一致。

代码覆盖面比 TinyDB 更广，属于运行成本轻、源码规模中等偏大的工具集，不是几十行入门应用。未运行多解释器／Windows／tox 全矩阵、格式／静态类型或文档构建。原生 socket 测试在无网络容器内使用本地 loopback，不接外部服务。产品 verifier 仍不支持原生 API 接入。

## 迭代路线

[20 步路线](./boltons-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

20 步为 6 项已在冻结提交复现的问题修复、14 项增强。issues-open.json 中包含上游 AI 辅助投稿的自述，本轮不采信其“修后通过”宣称，只采用本次原版实际复现和源码分析。日期月底、舍入规范化均保持旧默认并增加 opt-in 策略。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/boltons/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/mahmoud/boltons.git <checkout>
git -C <checkout> checkout --detach 4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --doctest-modules boltons tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run boltons -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/boltons/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
