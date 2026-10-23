# 真实项目审查：Agate

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[wireservice/agate](https://github.com/wireservice/agate)。面向人工数据分析的不可变类型化表，提供Decimal数值、分组/关联、统计、文件交换和轻量图表。
- 固定提交：[202796ada63357c275a2a5f8685a983e37bad9bf](https://github.com/wireservice/agate/tree/202796ada63357c275a2a5f8685a983e37bad9bf)；版本与运行要求：1.14.2，项目classifiers及实际Python3.12环境核对；pyproject未单列requires-python。
- 许可证：MIT。保留Christopher Groskopf与contributors版权和COPYING。正式源码Source明确wireservice/agate，非初始候选的agate-python/agate。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 250 个，1,217,170 字节 |
| Python 产品源码 | 100 个文件、6,948 行 |
| Python 测试文件 | 39 个、6,976 行 |
| 隔离依赖安装 | 7.951 秒，venv 96,596,671 字节 |
| 适用原生基线 | 396 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 1.414 秒，峰值子进程 RSS 51416 KiB |
| 容器运行 | 整体 1.915 秒，内存 256 MiB、PID 64，无 OOM |

运行依赖Babel、isodate、leather、parsedatetime（排除2.5）、python-slugify和pytimeparse；Windows额外tzdata。研究另装pytest、pytest-cov、lxml、cssselect，未编译Linux可选PyICU；本轮原生tests无需它即可全过，不声称已覆盖ICU语言排序配置。没有独立服务。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Table在创建时物化行、用TypeTester选择类型并调用DataType.cast，Row/Column/MappedSequence提供不可变访问；_fork生成新表保留类型/行名，TableSet用于分组后的聚合；Aggregation与Computation分别返回统计标量和派生列。读取Table、TypeTester、Number/DateTime、join/order_by、CSV/JSON与代表聚合/计算定义，现有Mean已支持TimeDelta，未重复列为新功能。

临时订单CSV按显式Number/Text类型读取，group_by与Sum得到A=3/B=4并写出真实JSON文件；复合索引连接抛tuple.index错误与相同值右列排除错误均复现。TimeDelta Mean=2秒为通过对照，Median明确不支持为增强缺口。

## 基线范围与限制

完整tests集合396通过、0失败／错误／跳过，无-k裁剪。lxml/cssselect已准备以运行相关HTML/SVG原生验证；未运行文档构建或其他平台。

Table会物化数据，轻量是本轮数据规模和运行成本，不表示无限数据流可用。未验证PyICU可选路径、Windows、多Python或重写成Rust/Arrow提案；不引入额外服务或将未来流式批次说成现有能力。平台原生接入未开始。

## 迭代路线

[20 步路线](./agate-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

20步为1个已复现列解析根因修复与19增强。原生多列group_by/pivot、cast、Number小数符、自定义Formula和Text可作为替代，路线没有把这些已有能力重复计数；新增的是明确的窗口、匹配策略、类型诊断和分析交付接口。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/agate/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/wireservice/agate.git <checkout>
git -C <checkout> checkout --detach 202796ada63357c275a2a5f8685a983e37bad9bf
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run agate -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/agate/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
