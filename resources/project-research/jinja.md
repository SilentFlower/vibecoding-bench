# 真实项目审查：Jinja

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[pallets/jinja](https://github.com/pallets/jinja)。
- 固定提交：[5ef70112a1ff19c05324ff889dd30405b1002044](https://github.com/pallets/jinja/tree/5ef70112a1ff19c05324ff889dd30405b1002044)，版本 3.2.0.dev。
- 许可证：BSD-3-Clause。已读LICENSE.txt；保留Pallets版权、三项再分发条件及免责声明。
- Python模板编译引擎，支持继承、宏、自动转义、沙箱及异步渲染；不要求Web应用、数据库或账号。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 107／1146887 |
| 产品 Python 模块／行数 | 25／14351（src/jinja2/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 10.49 秒，venv 87208816 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 911 通过、0 失败、0 错误、0 跳过、0 预期失败；另 0 个原生子测试通过；墙钟 3.79 秒 |
| 子进程峰值 RSS | 77652 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

Python≥3.10，核心MarkupSafe≥3；安装i18n额外Babel以及pytest/pytest-timeout/trio。所有实际解析版本记录于依赖冻结；未连接翻译服务。

最终911通过，0失败／错误／普通skip／xfail。没有以选择性排除问题测试换取通过；其他Python/OS矩阵未跑。

Lexer生成TokenStream，Parser构造nodes AST；CodeGenerator生成Python，Template通过Context和runtime宏/loop渲染。Environment._load_template与BaseLoader.load管理同步源码获取、模板和字节码缓存；async模式支持渲染但加载入口仍同步。已读真实filter、attribute getter、Include编译、宏签名、Undefined、meta符号分析、Package/FileSystem loader、流dump和AST位置定义。

## 原生使用场景和改进研究

独立原生场景使用DictLoader继承base/page并对中文尖括号标题自动转义，得到<h1>&lt;评审&gt;</h1>。原版实测发现9类可复现问题：Mapping urlencode错值、undefined误报escaped、indent空首行及换行策略（同族合并）、slice整除仍补值、显式None default失效、macro内无context include产生generator repr、async map→sort失败、meta条件赋值误报、负数幂常量/变量不一致。另核实PathLike stream、负索引属性、include显式实参和fallback imports缺少支持。已区分Jinja文档约定的幂左结合：2**3**2为64不独立算BUG；本轮只修复同AST常量折叠与运行时的不一致。

完整 [20 步路线](./jinja-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/jinja/`；固定源码当前位置 `/tmp/github-research-jinja-tzuvabrq/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/pallets/jinja.git <checkout>
git -C <checkout> checkout --detach 5ef70112a1ff19c05324ff889dd30405b1002044
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[i18n]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

使用独立临时检出、隔离HOME及venv，观察脚本同样在临时源码目录运行。未对s390x、Python3.14/PyInstaller的issue作复现结论；未把上游issue正文当作通过证据。以下11项增强均是显式新契约，尚未获上游承诺。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
