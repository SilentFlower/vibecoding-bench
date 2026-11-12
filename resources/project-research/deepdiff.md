# 真实项目审查：DeepDiff

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[qlustered/deepdiff](https://github.com/qlustered/deepdiff)。Python对象深度比较、内容Hash、搜索与Delta补丁工具，提供CLI和多种报告视图。
- 固定提交：[79e4379278b1cfdd8e9e3dccac364956908e8989](https://github.com/qlustered/deepdiff/tree/79e4379278b1cfdd8e9e3dccac364956908e8989)；版本与运行要求：9.1.0，Python>=3.10。
- 许可证：MIT。保留Sep Dehpour(Seperman)及contributors的LICENSE。原seperman/deepdiff当前官方重定向qlustered/deepdiff，pyproject Repository一致，以canonical身份仅计一次。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 183 个，3,128,371 字节 |
| Python 产品源码 | 18 个文件、9,677 行 |
| Python 测试文件 | 31 个、15,125 行 |
| 隔离依赖安装 | 46.165 秒，venv 389,875,384 字节 |
| 适用原生基线 | 1264 通过、0 失败、0 错误、44 跳过 |
| 基线进程 | 6.825 秒，峰值子进程 RSS 194480 KiB |
| 容器运行 | 整体 7.161 秒，内存 256 MiB、PID 64，无 OOM |

核心依赖cachebox>=5.2,<6与orderly-set>=5.5,<6；本轮为覆盖原生集合额外准备numpy/pandas/polars、orjson/pydantic/jsonpickle、日期/CLI/TOML及pytest-benchmark等上游对应测试依赖，实际大小/精确版本见安装证据。完整测试环境比核心运行包显著大，不能隐藏该成本；不需要独立数据库或云服务。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

DeepDiff在_diff中分派类型与自定义operator，路径过滤和无序匹配/Hash决定报告；DeepHash对对象内容归一化；DeepSearch找匹配；Delta保存增删改并支持bidirectional反向应用，默认不原地修改；SerializationMixin负责text/tree/JSON/flat输出，commands.py为实际文件CLI。读取了这些类构造契约、类型分派、时间/数字归一化、路径与Delta验证/序列化定义。

合成订单前后对象做DeepDiff，创建bidirectional Delta；before+delta得到after且after-delta回到before，真实写出after.json与diff.json并独立JSON读回。复现复数负虚部、date截断、datetime字典键、固定时区对象等4项问题；排除路径仍调用operator记录为未定策略增强。旧group_by=None/ignore_order数值类型问题当前已不复现，作为通过对照不计修复。

## 基线范围与限制

原生tests默认集合完整运行1264通过、44跳过、0失败/错误、9警告。44为36个需--runslow的缓存/多进程用例与8个上游明确skip/尚未实现用例；未传-k裁剪。运行过1项上游benchmark，其结果只作本次环境证据，不宣称跨机器性能。

初跑在NumPy等后台线程池+原生30线程测试叠加下撞PID64，保留thread-budget-preparation-attempt；随后仅把OPENBLAS/OMP/POLARS/MKL后台线程各限制1，仍用256MiB/PID64，全套重跑通过。9项fork多线程/jsonpickle弃用警告保留。未跑--runslow、nox多解释器、flake8/mypy、文档或所有多进程大负载。源码/测试依赖面较大，属于运行可控而非最小工程；平台须预制依赖及线程预算，尚未接入。

## 迭代路线

[20 步路线](./deepdiff-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

4项当前提交复现的问题修复+16增强；已存在glob路径、callable过滤、hasher、自定义operator、双向Delta、进度日志和多进程不重复计功能。两方combination merge、三方冲突合并与Delta组合交付目的不同，不能把普通base+delta称作同一种合并。每步仍需在真实候选路径冻结独立验收。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/deepdiff/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/qlustered/deepdiff.git <checkout>
git -C <checkout> checkout --detach 79e4379278b1cfdd8e9e3dccac364956908e8989
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run deepdiff -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/deepdiff/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。保留runtime-environment.json中的四个线程上限，否则完整原生测试会与PID64预算冲突；此为研究/验收依赖准备要求，不修改产品账号配置。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
