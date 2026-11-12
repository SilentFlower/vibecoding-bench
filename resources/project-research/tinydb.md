# 真实项目审查：TinyDB

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[msiemens/tinydb](https://github.com/msiemens/tinydb)。纯 Python 文档数据库，以 JSON 文件或内存保存多表文档，提供查询组合和更新操作。
- 固定提交：[edff96aeb2616402e9489d46e90a592c05565621](https://github.com/msiemens/tinydb/tree/edff96aeb2616402e9489d46e90a592c05565621)；版本与运行要求：4.9.0，Python >=3.10,<4。
- 许可证：MIT。复制时保留 LICENSE 中 Markus Siemens 的版权和许可文本。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 65 个，597,655 字节 |
| Python 产品源码 | 10 个文件、2,303 行 |
| Python 测试文件 | 9 个、2,202 行 |
| 隔离依赖安装 | 13.313 秒，venv 54,970,808 字节 |
| 适用原生基线 | 228 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 1.917 秒，峰值子进程 RSS 40500 KiB |
| 容器运行 | 整体 2.425 秒，内存 256 MiB、PID 64，无 OOM |

核心无 PyPI 运行依赖，不需要数据库服务。实测准备 pytest、pytest-cov 与 PyYAML，安装精确版本保存在冻结清单。第一次隔离直连 PyPI 下载超时已保留 direct-network-attempt 日志；随后只透传无凭据本机代理完成准备，执行容器始终无网络。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

database.py 管理存储、默认表和表句柄；table.py 对整库做读取—表更新—写回，并管理文档 ID 与查询 LRU；queries.py 构造带可缓存身份的路径谓词；storages.py 提供 JSONStorage/MemoryStorage；middlewares.py 是整库存储拦截扩展点。实际读取了这些类、操作和相关测试。官方 intro 明确不适合多进程／线程、索引或 ACID 场景，本路线保留单实例边界。

原生场景在临时 JSON 文件建立 orders 表，插入 A/B 两个订单、increment 修改数量，关闭重开后按 Query 检索与计数，真实落盘结果正确。额外实测了两种 storage 下 update_multiple 的一次性规则迭代器丢后续更新，以及 fragment 路径遗漏造成缓存串结果，均在当前完整提交复现。公开 API 和精确签名保存在同一 smoke 输出中。

## 基线范围与限制

完整 tests 原生业务集合，228 通过、无失败／错误／跳过。命令用 -o addopts= 仅关闭 pytest.ini 默认的覆盖率展示以保持取证输出简洁；没有选用 -k 或裁剪测试文件。

未运行 Pyright/MyPy、pycodestyle、文档构建或跨 Python／Windows 矩阵；不声称覆盖率百分比。上游 uv.lock 存在，本轮独立研究环境依实际安装结果冻结，未声称等同 uv 锁定环境。准备阶段首次命令过早启动时 pytest 尚未安装，准备尝试日志已保留，最终有效基线是在成功安装后重跑。当前 ProjectVerifier 的 app.py 协议尚不支持本工程原生 API，未完成平台接入。

## 迭代路线

[20 步路线](./tinydb-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

路线含 2 项已复现问题修复、18 项增强提案；没有把上游已修复的正则 flags、文档 ID 批量分配或字符串 any/all 问题重复计入。用户可通过标准 Python 组合实现部分增强，路线目标是同仓中有明确兼容契约的原生便捷能力。可选批处理和原子存储分别解决一次提交的逻辑边界与文件发布边界，不宣称通用数据库事务。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/tinydb/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/msiemens/tinydb.git <checkout>
git -C <checkout> checkout --detach edff96aeb2616402e9489d46e90a592c05565621
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -o addopts= -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run tinydb -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/tinydb/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
