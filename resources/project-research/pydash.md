# 真实项目审查：Pydash

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[dgilland/pydash](https://github.com/dgilland/pydash)。Lo-Dash风格Python函数式工具库，覆盖深路径对象、集合、函数组合、重试和链式调用。
- 固定提交：[ef6a6427e488e29e827e0e0819f2630ad3ff4cdc](https://github.com/dgilland/pydash/tree/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc)；版本与运行要求：8.1.0，Python>=3.10。
- 许可证：MIT。保留Derrick Gilland版权与LICENSE.rst。初始pydash/pydash实际是个人资料配置仓，已拒用并依据正式Homepage核对dgilland/pydash。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 78 个，1,026,935 字节 |
| Python 产品源码 | 15 个文件、17,884 行 |
| Python 测试文件 | 25 个、11,261 行 |
| 隔离依赖安装 | 7.252 秒，venv 50,486,263 字节 |
| 适用原生基线 | 2880 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 5.825 秒，峰值子进程 RSS 60820 KiB |
| 容器运行 | 整体 7.647 秒，内存 256 MiB、PID 64，无 OOM |

核心仅typing-extensions>3.10且排除4.6.0；原生测试用pytest，运行场景无需服务、云凭据或网络。静态mypy样例按上游tasks.py默认test(with_mypy_tests=False)排除；不是通过裁掉真实失败测试来得到基线。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

objects.py通过PathToken/base_get/base_set完成深路径与merge；collections与arrays提供iteratee驱动数据处理；functions.py有同步Flow、Debounce/Throttle等包装器；utilities.py管理memoize、retry、random、路径解析；Chain/ChainWrapper延迟执行方法但每个集合map仍可物化列表。读取了实际类、参数、原地修改规则和受限key防护，新增路径接口需保留该防护。

真实JSON文件读取嵌套订单，chain.filter→map(qty)→sum得到3并写回JSON文件核对。用模块实际导入的randint/uniform mock固定随机边界，证明单界与文档不符；falsey回调在3次retry后记录仍空。公开签名和候选入口缺口保存。

## 基线范围与限制

按上游默认test任务的范围运行src/pydash模块doctest与tests，忽略tests/pytest_mypy_testing静态样例：2880通过、0失败/错误/跳过。关闭addopts中的覆盖率展示/门槛，只报告功能集合，不声称100%coverage。

首轮误把reveal_type静态样例当运行测试导致351个相关失败，另2个真实子进程测试因自己覆盖PYTHONPATH而找不到typing_extensions；dependency-preparation-attempt保留。最终按官方范围并将离线依赖只读放进容器标准site-packages后完整重跑；无上游源码修改。未跑mypy、ruff、文档、跨Python和多平台。普通chain不是流式，未来并发/async增强须明确资源和取消语义。平台未接入。

## 迭代路线

[20 步路线](./pydash-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

2个当前提交已复现修复+18增强；原有retry退避/抖动/max_delay、路径转义、clone_deep、merge_with迭代器和防抖重入修复均已存在，不把它们重复计步。所有新函数、overloads、公开__all__与chaining类型暴露须在交付对应步骤同步，不能只增Python实现而遗漏包的类型契约。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/pydash/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/dgilland/pydash.git <checkout>
git -C <checkout> checkout --detach ef6a6427e488e29e827e0e0819f2630ad3ff4cdc
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -o addopts= -p no:cacheprovider --doctest-modules src/pydash tests --ignore=tests/pytest_mypy_testing --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run pydash -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/pydash/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。本仓源码在src，runner重跑使用 --pythonpath /src；标准site-packages只读挂载保证原生测试主动重设PYTHONPATH的子进程仍能加载typing_extensions。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
