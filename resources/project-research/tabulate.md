# 真实项目审查：Tabulate

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[astanin/python-tabulate](https://github.com/astanin/python-tabulate)。Python表格格式化库与CLI，支持多种文本标记/HTML/LaTeX、数字推断和宽字符对齐。
- 固定提交：[268615a5c27dc40e5c22454c07b44d5c50410da0](https://github.com/astanin/python-tabulate/tree/268615a5c27dc40e5c22454c07b44d5c50410da0)；版本与运行要求：浅克隆SCM实际版本0.1.dev1+g268615a5c，Python>=3.10；不将其冒称上游发布版。
- 许可证：MIT。保留Sergey Astanin与contributors版权及MIT许可。初始候选python-tabulate/tabulate为不存在路径，已由官方Homepage核对为astanin/python-tabulate。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 26 个，376,963 字节 |
| Python 产品源码 | 3 个文件、3,130 行 |
| Python 测试文件 | 9 个、6,078 行 |
| 隔离依赖安装 | 13.947 秒，venv 56,057,916 字节 |
| 适用原生基线 | 366 通过、0 失败、0 错误、17 跳过 |
| 基线进程 | 5.295 秒，峰值子进程 RSS 47924 KiB |
| 容器运行 | 整体 6.349 秒，内存 256 MiB、PID 64，无 OOM |

核心无强制第三方运行依赖；本轮安装pytest与widechars可选依赖wcwidth，精确版本冻结。numpy/pandas未安装，相关原生测试按上游条件skip。CLI无需独立服务；真实源码包含cli.py，不能使用别的已安装tabulate冒充。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

_normalize_tabular_data把映射/数据类/数组转换为行列；分隔行先移除再插回；_type/_format决定列数值表示，_wrap_text_to_colwidths负责换行；ANSI/可选wcwidth计算可见宽度；_format_table按TableFormat生成行/线；cli.py负责CSV/RSV/JSONL与文件输出。已读取实际tabulate签名、参数展开、类型/包裹、索引和CLI定义。

原生API渲染中文商品GitHub表；实际以python -m tabulate.cli从stdin读取CSV并输出临时Markdown文件，核对字段和行。复现5类差异：分隔行显式索引长度、无宽字符模式的BEL超链接、tuple参数展开、disable_numparse换行异常、空段落被吞。OSC8实测开启wcwidth时已正确，报告限定出错配置。

## 基线范围与限制

遵循pyproject/tox默认tests+模块doctest+README doctest完整运行：366通过、17跳过、0失败／错误。17项包含13个numpy/pandas可选分支及4个上游本来标记skip的数值/回归用例，-ra保留具体位置；不声称这些分支通过。

未跑numpy/pandas额外环境、ruff、跨Python/平台或LaTeX/Typst外部排版编译。当前wcwidth能处理BEL，原生无插件/关闭widechars路径仍有问题，不能泛称所有环境都错。SCM构建标签需在平台适配阶段固定。尚无原生verifier集成。

## 迭代路线

[20 步路线](./tabulate-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

20步=5个当前提交已复现修复+15增强。preserve_whitespace、break_long_words、列和表头对齐、JSONL CLI已存在，未重复计步。增强是围绕真实表格表示的可选接口与输出契约，不套用通用CRUD；每项正常/异常验收独立。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/tabulate/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/astanin/python-tabulate.git <checkout>
git -C <checkout> checkout --detach 268615a5c27dc40e5c22454c07b44d5c50410da0
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run tabulate -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/tabulate/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
