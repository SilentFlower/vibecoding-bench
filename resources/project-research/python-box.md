# 真实项目审查：python-box

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[cdgriffith/Box](https://github.com/cdgriffith/Box)。
- 固定提交：[a4c10e977b574114613431394b30412b50aaacce](https://github.com/cdgriffith/Box/tree/a4c10e977b574114613431394b30412b50aaacce)，版本 7.4.1。
- 许可证：MIT。保留LICENSE中2017–2026 Chris Griffith归属及依赖各自许可。
- 提供属性访问、可配置转换和多格式序列化的真实字典／列表对象；纯Python核心无必需依赖，Cython加速可选。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 51／262508 |
| 产品 Python 模块／行数 | 8／2654（box/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 12.55 秒，venv 58362607 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 159 通过、0 失败、0 错误、0 跳过、0 预期失败；另 0 个原生子测试通过；墙钟 1.09 秒 |
| 子进程峰值 RSS | 55276 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

运行核心无外部依赖，Python≥3.9。YAML／TOML／msgpack等为extras，测试额外依赖toon_format从官方requirements-test.txt指定Git仓准备；实际resolved commit与锁记录在toon-installation.json及requirements-frozen.txt。初次漏TOON造成5失败保留before-toon-dependency-*，补齐后159全过；不是产品缺陷。安装表耗时仅初始安装，TOON追加耗时未单独测量；环境字节数已更新到追加后，不能把表中耗时说成全依赖总耗时。

最终159通过、无失败／跳过；未安装Cython加速，未执行其二进制构建、多平台／类型／格式检查。

Box继承dict，在__setitem__中应用box_dots、camel_killer、recast和嵌套Box/BoxList转换；_box_config保存真实选项。BoxList维护列表元素转换；ConfigBox提供bool/int/float/list便捷cast。converters处理各格式，box_from_file按扩展名统一加载。已读取上述真实构造器、getitem/setitem、默认值、pickle/copy、merge_update和转换方法；已有统一文件读取、BoxList、keys(dotted)、safe_attr、box_dots_exclude、default callable、merge列表extend/unique及JSONL文件读取均不重计。

## 原生使用场景和改进研究

实际Box属性修改server.port后写JSON、box_from_file读回中文和6432成功，导入确认来自固定源码。实测：Box子类pickle后子节点降为Box；YAML点分key在父key之前会丢数据而反序保留；frozen_box中的列表嵌套Box无法to_yaml；default_box_create_on_get=False下链式赋值不附着；CamelCase转换改写外部字段名；默认list merge整体替换；YAML注释丢失；ScalarFloat未归一为精确builtin type；ConfigBox.bool("maybe")为True。后三类有已存在替代方案或策略意义，路线采用显式增强，不冒充统一BUG。

完整 [20 步路线](./python-box-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/python-box/`；固定源码当前位置 `/tmp/github-research-python-box-w82vl44r/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/cdgriffith/Box.git <checkout>
git -C <checkout> checkout --detach a4c10e977b574114613431394b30412b50aaacce
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[all,tomli,PyYAML]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

未运行账号镜像或真实业务配置，未发送上游消息。YAML roundtrip新模式与builtin归一化模式目标不同，必须显式选择，不能同时承诺保留格式对象和全部变成builtin。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
