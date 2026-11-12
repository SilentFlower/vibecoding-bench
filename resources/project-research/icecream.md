# 真实 GitHub 项目审查：IceCream

研究日期：2026-10-21。适合小型Python调试工具的累计工程，保留AST源表达式提取及真实依赖；路线关注表达式保真和可选调试体验。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./icecream-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[gruns/icecream](https://github.com/gruns/icecream)，元数据归档状态为 false。
- 完整固定提交：[05af3e95b0080162813bb017de90966bc75f3b91](https://github.com/gruns/icecream/tree/05af3e95b0080162813bb017de90966bc75f3b91)，包版本 2.2.0。
- 许可证：MIT。保留LICENSE.txt和源文件版权声明，未向上游发送任何消息。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

IceCreamDebugger.__call__使用真实调用Frame，通过executing.Source及asttokens恢复表达式，格式化参数并调用可配置outputFunction，最后原样返回实参。argumentToString采用singledispatch，默认safe_pformat和字符串特化；Timer提供同步装饰器/上下文；builtins.install/uninstall可安装ic到自定义内置名称。无独立CLI或服务，原生入口是ic、ic.format和Debugger实例。已读完整核心、计时和安装定义及测试，不重写成同构app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 25／140426 |
| 产品源码 | 786 行 Python，5 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 实际必需colorama>=0.3.9、Pygments>=2.2.0、executing>=2.1.0、asttokens>=2.0.1；原生测试另装上游tox使用的sympy及pytest/报告工具，精确实际版本冻结。上游没有本轮统一lock，安装本地setup.py项目 |
| 外部系统 | 无数据库、云API或必需系统包；本轮不装Qt/Pygame/IDE，不用真实Windows控制台 |
| 安装耗时 | 27.53 秒；受缓存与网络影响 |
| 独立 venv 大小 | 113,039,603 字节，含 pip 和本轮测试工具 |
| 原生基线 | 65 通过、0 失败、0 错误、0 跳过 |
| 测试进程墙钟／峰值 RSS | 1.23 秒／61,832 KiB |

按上游unittest发现整个tests，使用不拦截stdout的原生TextTestRunner，执行后生成JUnit：65通过、0失败/错误/跳过。含计时、格式、颜色、Sympy和builtin安装。未执行mypy/tox外包装、多Python、Qt/Pygame/Jupyter/调试器或实机Windows；Windows清理问题仅通过模拟平台且mock init/deinit验证Python控制流，不称实机Win32已通过。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

真实源码文件里用独立Debugger检查value+1，返回值8不变；outputFunction捕获实际“value+1: 8”，写入临时文本文件后重读确认。20项观察全部通过原生入口、当前签名/字段或有界模拟路径核对，临时目录自动删除。

实证两个基础问题：*args展开被AST节点数量zip截断，输出漏值；Windows颜色上下文异常退出不执行deinit。其余18项为增强提案，包含可视字符串、可重入/异步计时、稳健repr、配置校验/作用域、模块过滤、限定名、每次格式选项、颜色环境、无上下文的快速路径、结构化事件、logging适配、函数跟踪、输出预算、文件输出、对象字段和可撤销安装。增强会改变或新增行为，未把所有缺口都当成既有BUG。

已经支持源不可见时只显示值并发warning、字面参数不重复显示表达式、noColor、use_stdout/use_stderr、lineWrapWidth、singledispatch注册/注销、同步Timer、禁用后原样返回值和自定义outputFunction；这些不能照旧issue重复计步。没有计划建立新的日志服务、异步发送队列或通用日志框架；logging仅适配标准库。源码中英文注释保留，本轮未改上游。

## 二十步路线与接入边界

20项为2项复现修复和18项增强。控制字符/引号/不可见字符作为一种可视字符串能力合并；异步计时与函数调用追踪不同，后者输出参数/返回值，前者计量await执行区间。来源包含已读上游#221/#220/#125/#178/#174/#146/#32/#31/#109/#246及原生源码场景。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有verifier仍是旧app.py协议；后续原生验收须从候选导入icecream，真实源文件执行以验证executing/asttokens，而非仅用python -c导致源不可见后误以为表达式逻辑通过。冻结精确依赖并离线使用，输出/返回值/文件效果累计回归。512MiB/PID128结果不等于默认256MiB预算、跨平台或已接入生产。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/icecream/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/gruns/icecream.git <checkout>
git -C <checkout> checkout --detach 05af3e95b0080162813bb017de90966bc75f3b91
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest sympy unittest-xml-reporting
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run icecream baseline -- \
  /evidence/native_unittest.py
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run icecream observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
