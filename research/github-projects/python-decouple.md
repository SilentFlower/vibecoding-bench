# 真实项目审查：python-decouple

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[HBNetwork/python-decouple](https://github.com/HBNetwork/python-decouple)。
- 固定提交：[0573e6f96637f08fb4cb85e0552f0622d36827d4](https://github.com/HBNetwork/python-decouple/tree/0573e6f96637f08fb4cb85e0552f0622d36827d4)，版本 3.8。
- 许可证：MIT。保留 LICENSE 及原始维护者归属。setup.py旧url指向henriquebastos，研究以官方当前HBNetwork仓库和完整commit冻结。
- 把进程环境、.env／INI／secret目录中的配置转换为Python类型；核心单模块、无服务或第三方运行依赖。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 30／50812 |
| 产品 Python 模块／行数 | 1／316（decouple.py） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 8.18 秒，venv 50417400 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 67 通过、0 失败、0 错误、0 跳过、0 预期失败；墙钟 0.47 秒 |
| 子进程峰值 RSS | 75364 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心无外部依赖。历史requirements.txt把pytest锁在3.2（不适配Python3.12）；本轮使用pytest9.1.1与mock实际执行原生用例，精确版本冻结。首轮未装mock导致collection3错误，before-mock-*保留；补齐mock后67项全过。未安装发布／doc工具。

最终67通过、0跳过／失败／错误；未运行旧Python、Windows、IPython、zipapp实际环境，也未把源码分析的跨驱动问题描述为本轮实机复现。

Config.get按os.environ→repository→default优先取值，再将bool特殊转换或调用cast；AutoConfig按SUPPORTED顺序向祖先查settings.ini/.env并懒加载一次。RepositoryIni用ConfigParser，RepositoryEnv逐行split第一个等号、去包围引号，RepositorySecret在构造时读取目录全部条目。Csv基于shlex，Choices把结果转换后检查候选集合。以上源码完整读取；已有search_path、Csv自定义delimiter/cast/post_process、Choices、secret目录读取与默认值不重算新增能力。

## 原生使用场景和改进研究

原生合成.env读取PORT=5432转int、DEBUG=true转bool及中文NAME，确认导入冻结源码。实测Csv丢反斜杠、#后文本和空字段；RepositoryEnv环境键contains为True但getitem KeyError；RepositoryEmpty缺键返回None；UTF-8 BOM进入键名；INI URL中的%20触发插值错误；secret目录含子目录抛IsADirectoryError；export被当键名一部分。后面几个为当前能力边界，路线按opt-in增强和明确策略处理，不一概称BUG。所有环境patch仅使用合成映射并立即恢复。

完整 [20 步路线](./python-decouple-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/python-decouple/`；固定源码当前位置 `/tmp/github-research-python-decouple-rtz319wc/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/HBNetwork/python-decouple.git <checkout>
git -C <checkout> checkout --detach 0573e6f96637f08fb4cb85e0552f0622d36827d4
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

未运行正式账号镜像或真实.env／/run/secrets，未构造云插件。扩展主要在现有查找、仓库和cast接口上演进；不把通用.env解析所有语法直接宣称已兼容Bash或python-dotenv。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
