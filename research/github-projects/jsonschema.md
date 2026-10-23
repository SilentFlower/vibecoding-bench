# 真实项目审查：jsonschema

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema)。
- 固定提交：[c497561ea0a95f5aac09cd63d15eb1420eb7bbec](https://github.com/python-jsonschema/jsonschema/tree/c497561ea0a95f5aac09cd63d15eb1420eb7bbec)，版本 固定提交安装版本见 requirements-frozen.txt（VCS 构建）。
- 许可证：MIT。保留 COPYING；可选格式依赖选择 format-nongpl extra，并保留各依赖自身许可。
- Python JSON Schema 多草案验证库，支持本地Registry引用、错误树和格式检查；不需数据库、云账号或远程模式服务。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 627／3565201 |
| 产品 Python 模块／行数 | 37／11645（jsonschema/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 37.89 秒，venv 93156785 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 8297 通过、0 失败、0 错误、232 跳过、0 预期失败；墙钟 21.97 秒 |
| 子进程峰值 RSS | 139328 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心 attrs、jsonschema-specifications、referencing、rpds-py（带预编译扩展）；Python ≥ 3.12。本轮安装format-nongpl额外格式器、pytest、virtue、jsonpath-ng，冻结精确版本。没有构建Rust源码或启动服务；原生引用场景只用内存URNRegistry，不发HTTP。

8297 通过、232 跳过、0 失败／错误。跳过是上游明确的 ECMA regex／Unicode property、复杂email、leap seconds、完整hostname/idn-hostname、部分vocabulary和严格duration能力边界，详细数量见baseline-tests.log；并非依赖没装就宣称格式全支持。类型检查、pyperf基准矩阵、文档构建和多Python版本未跑。

validators.create 生成带schema、registry、format_checker的Validator类，预选关键字函数；iter_errors／descend按位置补全ValidationError。_legacy_keywords维护旧草案规则，_keywords与_utils维护2020-12及已评估集合，_format按格式登记checker及可转换异常。exceptions._Error维护path/schema_path/context父链，best_match做错误选择。已读真实方法；现有TypeChecker扩展、registry、iter_errors惰性、is_valid首错、可选format checker和CLI --base-uri均不重算新能力。

## 原生使用场景和改进研究

原生场景使用纯本地Registry的urn引用校验server.port，5432通过、0给minimum错误与port路径，确认加载固定checkout。原版实测复现：2019-09 items=True+unevaluatedItems TypeError；含末换行属性的json_path选到另一个合法键；iterator子context无parent；regex深嵌套RecursionError与冲突flags ValueError；duration极大指数decimal.Overflow；2020-12相对指针index manipulation被拒；date-time／uri／uri-reference／hostname尾换行被接受而time对照正确拒绝。缺陷族按共享处理合并，不为不同格式或异常拆步。

完整 [20 步路线](./jsonschema-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/jsonschema/`；固定源码当前位置 `/tmp/github-research-jsonschema-ofvyhs6w/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/python-jsonschema/jsonschema.git <checkout>
git -C <checkout> checkout --detach c497561ea0a95f5aac09cd63d15eb1420eb7bbec
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[format-nongpl]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

原生完整测试在独立临时检出和HOME／venv实跑，未跑正式账号镜像。格式checker依赖版本也已冻结，不能把可选格式的局限推广成全部格式失效。性能改进仅源码识别，本轮未用大规模压力或未实现补丁宣称性能提升。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
