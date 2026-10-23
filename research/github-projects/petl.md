# 真实项目审查：PETL

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[petl-developers/petl](https://github.com/petl-developers/petl)。基于可重复迭代惰性表的 Python ETL 工具，连接 CSV/JSON/SQL 等输入输出与转换、关联、聚合、校验。
- 固定提交：[cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b](https://github.com/petl-developers/petl/tree/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b)；版本与运行要求：源码固定提交；浅克隆通过 setuptools-scm 实际构建版本为 0.1.dev1（未将其冒称上游已发布版本），声明 Python >=2.7 且排除3.0—3.3。
- 许可证：MIT。保留 Alistair Miles 的版权与 MIT 许可，格式适配的可选第三方组件另依其许可证准备。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 239 个，1,778,519 字节 |
| Python 产品源码 | 61 个文件、21,075 行 |
| Python 测试文件 | 73 个、18,435 行 |
| 隔离依赖安装 | 10.534 秒，venv 57,650,590 字节 |
| 适用原生基线 | 912 通过、0 失败、0 错误、23 跳过 |
| 基线进程 | 10.855 秒，峰值子进程 RSS 60024 KiB |
| 容器运行 | 整体 11.539 秒，内存 256 MiB、PID 64，无 OOM |

核心无强制第三方运行依赖，可选 extras 涵盖 pandas/numpy、SQLAlchemy、Excel、Avro、PyTables、远程等。本轮只准备 pytest>=7.4,<9、pytest-cov>=4,<7、pytest-timeout 和 setuptools，遵循 Python3.12 上游测试版本范围，不装大型格式／远程服务。实际依赖版本冻结；正式适配应固定 SCM 构建元数据，不能把浅克隆计算版本当发布版。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

util.base.Table 统一惰性视图；transform 模块以 __iter__ 管道实现表转换；io.sources 管理 File/Gzip/BZ2/ZIP/远程源，CSV 在 Python3 走 csv_py3，io.json 的生成器视图用临时文件支持重复遍历；sort 可溢写磁盘，关联／聚合复用排序；XML 当前整树读取并使用模板写出。上述定义和具体路线的现有入口均实际读取。

在临时文件写订单 CSV，fromcsv→convert(int)→aggregate(sum) 得 A=3/B=4，再 tocsv 并原生读回核对。复现 XML 数据 A&B 未转义使独立 ElementTree 抛 ParseError，以及单表重复表头 cat 把 (1,2) 改成 (1,1)。同时记录新拟议入口缺失和现有签名。

## 基线范围与限制

执行 petl 全目录原生测试（没有 -k 裁剪），912 通过、23 跳过、0失败／错误、2警告。沿用 pytest.ini 的 *_py2.py 与 io/db.py doctest 排除；本轮未启用全模块 doctest。跳过为可选 fastavro/bcolz/numpy/pandas/PyTables/SQLAlchemy/gspread/Whoosh/Excel/intervaltree/fsspec/SMB、MySQL/Postgres驱动与Python2专用分支；1项上游 URL XML 测试因隔离无网络自行 skip。具体分组与次数见原始 -ra。

2项 PytestUnraisableExceptionWarning 来自原生 test_fromdb 在关闭 SQLite 后回收生成器、cursor.close 抛 ProgrammingError，已如实保留，不将全绿说成无警告。未跑可选格式／独立数据库／远程服务或跨 Python 矩阵；Parquet等新增可选适配需在实施该步再测安装、内存和离线成本，不计本轮已具备。运行轻但 API/源码面较大，非最小入门工程。平台原生适配未开始。

## 迭代路线

[20 步路线](./petl-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

2 项当前提交复现的数据正确性问题、18 项增强。valuecounter 的 tuple 参数现已明确文档为 *fields，fromdicts generator 与 .dicts() 兼容已存在，不把旧 issue 当待修复；现代 CSV 的 NUL、表达式安全与跨月等未决策略不擅自定义为20个 BUG。路线保留已有反复迭代、缺失值和可选依赖模型。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/petl/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/petl-developers/petl.git <checkout>
git -C <checkout> checkout --detach cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider petl --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run petl -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/petl/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
