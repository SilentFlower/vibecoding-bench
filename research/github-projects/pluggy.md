# 真实项目审查：Pluggy

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[pytest-dev/pluggy](https://github.com/pytest-dev/pluggy)。
- 固定提交：[0224f79fc75efadaafe24dbab9deee2ff616ecd7](https://github.com/pytest-dev/pluggy/tree/0224f79fc75efadaafe24dbab9deee2ff616ecd7)，版本 1.7.1.dev6+g0224f79fc（补取官方tag/history后的SCM值）。
- 许可证：MIT。已读LICENSE，保留2015 Holger Krekel版权及许可。
- Python插件注册与hookspec/hookimpl调用机制，支持wrapper、历史重放、默认参数、入口点发现和调用监控；核心零外部运行依赖，不需要pytest应用才能使用。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 81／410610 |
| 产品 Python 模块／行数 | 13／2097（src/pluggy/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 8.38 秒，venv 52053293 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 225 通过、0 失败、0 错误、0 跳过、0 预期失败；另 0 个原生子测试通过；墙钟 0.87 秒 |
| 子进程峰值 RSS | 86804 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

Python≥3.10。按testing dependency group安装pytest≥8、pytest-benchmark、coverage。浅检出先补取官方完整history/tags使SCM得到原生1.7.1.dev版本，避免错误0.1值与pytest依赖冲突；tag-history-fetch.log保留该准备步骤，冻结工作树commit不变。

225全部通过，无普通skip/xfail；未改变测试或降低warnings=error。pytest-benchmark已安装但默认不收testing/benchmark.py，未宣称性能benchmark通过。未跑其他Python/OS矩阵。

PluginManager发现静态标记，构造HookImpl并验证参数名，然后注册到HookCaller。HookCaller应用hookspec默认值、复制实现列表，交_execution._multicall逐项调用并展开/回退wrapper；historic记录参数供延后注册回放。入口点映射关联distribution，monitoring包装整个_hookexec。已读真实_manager/_caller/_execution/_impl/_decorators/_config和追踪实现。

## 原生使用场景和改进研究

真实场景注册带中文输入的render协议和插件，pm.hook.render(value=中文)返回[render:中文]。固定源码复现6类问题：historic持有调用者kwargs引用；declined入口点误计数并在列distribution时KeyError；带默认值的位置专用参数被作关键字传入；相等但不同对象误判已注册；add_hookspecs验证/历史重放失败留下部分状态（同族合并）；python -O下unregister省略/未注册对象校验消失。现有register先验证全部hookimpl、subset_hook_caller、sync monitoring、warn_on_impl_args和标记器静态类型已存在，不重复当新增。

完整 [20 步路线](./pluggy-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/pluggy/`；固定源码当前位置 `/tmp/github-research-pluggy-fx39lje5/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/pytest-dev/pluggy.git <checkout>
git -C <checkout> checkout --detach 0224f79fc75efadaafe24dbab9deee2ff616ecd7
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

独立临时检出、HOME、venv；入口点场景用合成Distribution/EntryPoint对象，不加载用户机器插件。-O观察仅启动本轮venv子进程，无真实插件执行。以下14项增强明确不代表上游采纳；尤其#705上游倾向不实现before/after排序，试点仍可在明确环检测/兼容边界下研究。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
