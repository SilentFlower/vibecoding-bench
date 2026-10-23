# 真实项目审查：CLI Helpers

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[dbcli/cli_helpers](https://github.com/dbcli/cli_helpers)。
- 固定提交：[e2538b1d338ead4ed803ec0017017bf6779a380b](https://github.com/dbcli/cli_helpers/tree/e2538b1d338ead4ed803ec0017017bf6779a380b)，版本 2.15.2。
- 许可证：BSD-3-Clause。保留 LICENSE 和 dbcli 归属；不使用作者名为派生内容背书。
- 供数据库等命令行客户端使用的表格、CSV／TSV／JSONL 输出与分层配置助手；本轮无数据库服务器或凭据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 59／146716 |
| 产品 Python 模块／行数 | 12／1687（cli_helpers/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 11.73 秒，venv 58242100 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 92 通过、0 失败、0 错误、4 跳过、0 预期失败；墙钟 0.97 秒 |
| 子进程峰值 RSS | 90576 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

运行依赖 configobj ≥ 5.0.5、tabulate[widechars] ~=0.10.0，styles extra 使用 Pygments。本轮另装 pytest／pytest-cov，精确版本冻结在 requirements-frozen.txt；没有安装完整文档／发布工具链。

4 项跳过：1 项专用于缺少 Pygments 的分支（本轮已安装）、1 项 Windows、2 项 macOS；未伪报为本机全平台验证。

TabularOutputFormatter 选取 _output_formats 注册项，推断 column_types 后依序运行 preprocessors，再调用格式适配器。CSV／TSV／JSONL 原生生成字符串行；tabulate 分支提供多种表格。config.py:Config 包装 ConfigObj，从 additional/system/user 文件读取并 UserDict.update 合并。已读取格式器、各适配器、preprocessors、utils、Config 构造／读写定义及原生回归。已有自定义 formatter、额外 preprocessors、Unicode 表格、per-column 时间格式和二进制 hex 均作为既有能力。

## 原生使用场景和改进研究

原生场景从公开 format_output 导出 Unicode CSV 和 NULL，实际逐行核对 id,name／1,你好／2,，确认从冻结 checkout 导入。实测已确认：missing_value=N/A 泄漏给新 formatter 实例；行本身是一次性生成器时列推断耗尽行并输出空行；直接 JSON 适配器在 generator headers 的第二条记录失败；重复 JSON 列名静默覆盖；Decimal 经 float 发生精度损失；NaN 被输出为非严格 JSON；max_width=0／1／2 的截断结果反而超宽；TSV 字面反斜杠 n 与换行导出相同；Config 重读保留已删顶层 b 且来源列表重复，坏行警告后仍返回部分内容和 valid=True。需兼容的策略作为 opt-in 增强，明确确定的状态泄漏／迭代耗尽／非法截断作为修复。

完整 [20 步路线](./cli-helpers-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/cli-helpers/`；固定源码当前位置 `/tmp/github-research-cli-helpers-rmm0sbd9/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/dbcli/cli_helpers.git <checkout>
git -C <checkout> checkout --detach e2538b1d338ead4ed803ec0017017bf6779a380b
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[styles]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

只执行独立临时检出和 HOME 的 Python 原生基线；没有运行账号镜像、Windows/macOS、真实数据库客户端、格式或文档构建。未建立完整冻结验收。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
