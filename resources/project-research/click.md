# 真实项目审查：Click

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[pallets/click](https://github.com/pallets/click)。
- 固定提交：[2247b35ea1c47c727d7a06e51fa280e12a863ff6](https://github.com/pallets/click/tree/2247b35ea1c47c727d7a06e51fa280e12a863ff6)，版本 8.6.0.dev。
- 许可证：BSD-3-Clause。保留 LICENSE.txt 的版权、许可条件和免责声明。
- 组合式 Python CLI 工具包，提供命令组、参数类型、终端交互、补全和测试驱动；无数据库、Web 服务或云凭据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 178／1687127 |
| 产品 Python 模块／行数 | 17／12930（src/click/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 5.27 秒，venv 50130916 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 2262 通过、0 失败、0 错误、24 跳过、1 预期失败；墙钟 9.10 秒 |
| 子进程峰值 RSS | 135704 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

产品无必需第三方运行依赖；本轮仅安装冻结检出的源码和 pytest，实际版本见 requirements-frozen.txt。pyproject.toml 声明 Python ≥ 3.10，构建用 flit_core；没有安装文档、ruff、mypy、pyright 或 tox 全平台矩阵。

24 个显式跳过为 Windows msvcrt 输入、Windows 编辑器路径和 Windows-only 测试；tests/test_chain.py::test_group_chaining 为上游既有 xfail，单独保留，不冒充成功。31,000 个 stress 组合按上游默认 addopts 排除，未称为全量压力基线。日志没有新增失败。

实际数据路径为 decorators 构造 Command／Option → Context 和 _OptionParser 解析原生 argv → ParamType 转换与 ParameterSource 记录 → Command.invoke 执行回调和清理资源。core.py 管共享协议，types.py 管类型，formatting.py／termui.py 管帮助与交互，shell_completion.py 管补全，testing.py 提供 CliRunner。已读取这些公开构造器与相关方法；现有 Context.formatter_class、Argument.help、PowerShell 补全和 CliRunner 的 fd 捕获已存在，不能再算新增能力。

## 原生使用场景和改进研究

observe.py 实际用 CliRunner 执行带 Unicode 参数的命令，将“你好，工程”写入临时文件后读回，确认 click.__file__ 来自冻结 checkout。另实测：ClickException 的 Python 3.11 notes 不显示；multiple 选项帮助没有重复省略号；to_info_dict 没有 usage；直接 CLI 调用的来源有值但 ctx.invoke 来源为 None；atomic=True 写相同内容仍替换 inode；exists=False 仍接受现有文件；帮助中的 %(prog)s 保持字面；Choice 接受工厂函数抛 TypeError，Option(nargs=-1) 被明确拒绝。上述多数是现有策略或缺少便利接口，本路线作为显式增强处理，不统称 BUG。其余缺口通过实际源码、公开签名与对应官方 issue 核对。

完整 [20 步路线](./click-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/click/`；固定源码当前位置 `/tmp/github-research-click-p92aivkg/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/pallets/click.git <checkout>
git -C <checkout> checkout --detach 2247b35ea1c47c727d7a06e51fa280e12a863ff6
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

本轮使用 /tmp 下无业务祖先的独立检出、独立 HOME 与 venv，未运行账号镜像容器、Windows、交互 TTY、文档构建或类型检查；适用默认原生测试和库驱动 CLI 场景已跑，不能推导所有平台能力通过。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
