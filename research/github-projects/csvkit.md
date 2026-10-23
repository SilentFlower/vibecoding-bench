# 真实项目审查：CSVKit

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[wireservice/csvkit](https://github.com/wireservice/csvkit)。真实CSV命令行工具套件，提供选择、筛选、清洗、关联、排序、统计、JSON/SQL/Excel等交换。
- 固定提交：[6d19c625214977ab2988e674441ca24638bc12d3](https://github.com/wireservice/csvkit/tree/6d19c625214977ab2988e674441ca24638bc12d3)；版本与运行要求：2.2.0，Python>=3.10。
- 许可证：MIT。保留Christopher Groskopf与contributors版权和COPYING。Agate是独立依赖及独立上游，不把依赖源码重复计为本仓。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 211 个，40,910,036 字节 |
| Python 产品源码 | 23 个文件、3,510 行 |
| Python 测试文件 | 23 个、3,056 行 |
| 隔离依赖安装 | 17.608 秒，venv 114,854,662 字节 |
| 适用原生基线 | 351 通过、0 失败、0 错误、4 跳过 |
| 基线进程 | 10.213 秒，峰值子进程 RSS 73600 KiB |
| 容器运行 | 整体 12.013 秒，内存 256 MiB、PID 64，无 OOM |

实际运行依赖agate>=1.12及agate-excel/dbf/sql、openpyxl、SQLAlchemy、xlrd和传递依赖，安装规模比单文件库高，未隐藏Excel/数据库适配成本。原生SQLite及随仓Excel/DBF例子无需额外服务。zstandard是可选extra，本轮未安装；不声称外部数据库/远程服务通过。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

CSVKitUtility集中argparse、文件/压缩源、reader/writer选项与类型推断；各utilities实现真实命令，csvclean通过RowChecker累计结构化错误，类型化排序/统计/JSON依赖agate，SQL通过SQLAlchemy/agate-sql执行，GeoJSON转换器保留id和geometry。源码有Windows _expand_args，未误称所有平台没有glob；新路线清单模式强调确定顺序和跨平台。

三个真实CLI子进程串接：csvcut从临时订单文件选sku/qty，csvgrep筛A，csvsort降序数量，再写selected.csv并由标准csv.reader独立读回A=2/A=1。记录clean/grep/sort/sql2csv/json/stack真实argparse选项，增强缺口不靠旧issue状态臆测。

## 基线范围与限制

完整tests集合351主项通过，另31 subtests通过，4项Windows专属跳过；0失败/错误，34警告（嗅探/重复空列/Excel扩展等原生日志保留）。JUnit测试计数包含subtests。按官方CI设置LANG/LC_ALL=en_US.UTF-8；初次C.UTF-8导致千分位期望失败，locale-preparation-attempt保留，环境纠正后全量重跑通过。

未执行Windows、独立PostgreSQL/MySQL、zstandard、多Python、文档构建/格式检查。locale是原生测试的重要环境条件，不能把C locale显示差异直接当产品BUG。当前全套运行只需256MiB，但依赖环境包含Excel生态；平台部署需预制离线依赖并固定源版本。未接入正式项目库。

## 迭代路线

[20 步路线](./csvkit-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

20步均为增强提案，来自具体上游请求和固定源码实际入口，不声称发现20个BUG。csvclean本来有CSV错误表、csvstat本来支持JSON、csvsort本来ignore-case、csvlook本来有max-rows、CSV压缩与Windowsglob已存在，路线只扩展缺失的用户行为，未重复计步。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/csvkit/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/wireservice/csvkit.git <checkout>
git -C <checkout> checkout --detach 6d19c625214977ab2988e674441ca24638bc12d3
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run csvkit -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/csvkit/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。CSVKit重跑须保留runtime-environment.json内官方CI使用的en_US.UTF-8，runner将只读依赖挂到容器标准site-packages，确保子进程也能加载它们。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
