# 真实项目审查：Confuse

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[beetbox/confuse](https://github.com/beetbox/confuse)。
- 固定提交：[bf42783301ac4e9c640328ec95486952fd599ce6](https://github.com/beetbox/confuse/tree/bf42783301ac4e9c640328ec95486952fd599ce6)，版本 2.3.0。
- 许可证：MIT。已读LICENSE，保留2015 Adrian Sampson版权及许可。
- 轻量YAML配置库，按优先级组合配置来源，以惰性ConfigView读取、模板校验/转换、路径解析和带默认注释的YAML输出服务本地应用。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 47／414905 |
| 产品 Python 模块／行数 | 7／2399（confuse/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 7.12 秒，venv 55452660 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 299 通过、0 失败、0 错误、1 跳过、0 预期失败；另 0 个原生子测试通过；墙钟 0.82 秒 |
| 子进程峰值 RSS | 75120 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

Python≥3.10，核心PyYAML与Python<3.13的typing_extensions；本轮pytest、click、tomli及其解析依赖冻结。发行工具的Sphinx/pandoc不属于本轮产品基线，未安装。

299通过，0失败/错误，1个原生skip：test/extra/test_release.py无法导入extra.release（无Sphinx）。跳过的是发布文档转换辅助工具，不是配置产品入口；没有声称发布工具通过。未跑其他Python/OS、风格/类型或文档构建。

RootView持有ConfigSource优先级列表，Subview.resolve沿父view逐来源遍历。get把参数经as_template转换后求值；flatten递归组合映射。YamlSource/EnvSource加载原始字典，build_dict还原嵌套参数；MappingTemplate/Sequence/Choice/Filename各自转换，Configuration.dump经定制Dumper并恢复默认文件注释。已读相关真实定义、共享build_dict、source.reload与redaction路径。

## 原生使用场景和改进研究

真实原生使用：临时YAML含中文name和port，经set_file再set_args覆盖port，MappingTemplate验证返回中文和9000。固定原版复现6类BUG：完整YAML环境/点号CLI覆盖的叶冲突、list下Subview.set破坏列表、尾注释dump抛StopIteration、校验所得AttrDict列表dump失败、Yaml/EnvSource重新load残留已删除键（同族合并）、list中的redaction未遮蔽synthetic值。另观察frozenset Choice不支持、get无模板只取首source、OneOf字符串是默认值而非literal、21:00解析为1260、原生无freeze/save/override/explain。list作为OneOf的旧#190在当前源码已经支持，明确排除。

完整 [20 步路线](./confuse-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/confuse/`；固定源码当前位置 `/tmp/github-research-confuse-zsdq47_x/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/beetbox/confuse.git <checkout>
git -C <checkout> checkout --detach bf42783301ac4e9c640328ec95486952fd599ce6
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

原生配置发现不读取真实HOME：基线在独立HOME，场景用read=False与合成临时文件/环境，patch.dict(clear=True)后恢复。以下增强只提出本试点明确新API契约，不把YAML1.1既有行为或未声明支持的frozenset当现版承诺。未实施路线、未变更默认解析规则。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
