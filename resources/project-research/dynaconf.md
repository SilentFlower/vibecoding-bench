# 真实项目审查：Dynaconf

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[dynaconf/dynaconf](https://github.com/dynaconf/dynaconf)。
- 固定提交：[32f38478350a80020e7aab60a3cbd29dd7f8d9ea](https://github.com/dynaconf/dynaconf/tree/32f38478350a80020e7aab60a3cbd29dd7f8d9ea)，版本 3.3.0.dev0（VERSION与原生安装）。
- 许可证：MIT；随附vendor许可同时保留。已读主LICENSE（2015 Bruno Rocha）和vendor_licenses下dotenv/Click的BSD-3-Clause及Box/Tomli/Toml/ruamel.yaml的MIT文本，不能只携带主仓许可遗漏vendored归属。
- 分层环境配置库，支持文件/环境变量/惰性插值、校验、合并、加载历史与CLI，含typed技术预览；本轮限定本地文件/内存配置，不调用外部秘密服务。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 955／7087435 |
| 产品 Python 模块／行数 | 112／37006（dynaconf/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 59.17 秒，venv 173350555 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 566 通过、0 失败、0 错误、0 跳过、1 预期失败；另 0 个原生子测试通过；墙钟 43.21 秒 |
| 子进程峰值 RSS | 139972 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

Python3.12；主包声明零外部依赖但内置多个vendored库。安装test extra（pytest/cov/xdist/mock、Flask/Django、Redis/hvac客户端、toml/configobj/commentjson、pytest-docker、boto3、IPython等）实际版本精确冻结；客户端安装不等于运行Redis/Vault/Docker服务。总体955跟踪文件/约7MB，Python总行数含vendor与vendor_src，不冒充纯手写核心体积；覆盖报告测量核心3085条statement。

566通过、0失败/错误/普通skip，1原生xfail：test_list_enclosed_type_with_multi_args；17个integration由上游本地test_only选择器排除。78条原生warnings（typed预览、弃用、测试刻意缺文件等）原样记录，没有屏蔽换通过。未跑mypy、功能脚本、外部Redis/Vault/云/Django集成和全平台矩阵。

LazySettings初始化Settings；Settings经各BaseLoader、env_loader载入，DynaBox/BoxList实现大小写访问和惰性值求值。set/update串联parse_conf_data、object_merge、source metadata和Validator；ValidatorList已有validate_all聚合。typed.Dynaconf从schema注解提取默认和validators再构造LazySettings，Options仅有有限初始化参数；CLI和inspect工具已能导出加载历史。已读这些真实定义及入口，不把已有aggregate/provenance/env context再列新功能。

## 原生使用场景和改进研究

真实场景从临时TOML读取default中文name、production port覆盖为9000，无真实.env。复现3类修复：load_file接受module对象即便silent=False也静默None；共享when Validator被首个dev校验持久赋envs，导致prod负port错误通过（新建validator对照拒绝）；update(data,OTHER=2)修改调用者data。嵌套list取出后append未保留、每次读返回新对象，作为显式引用模式增强；@merge_unique现版已保持red/green/blue，旧#1167排除。PathLike strict加载观察到缺前缀env节KeyError，这是原strict缺环境策略（原生test_toml_loader有对应约定），不误报Path类型BUG。tuple多参数和Any注解原生SchemaError、typed额外字段默认保留都已核实。

完整 [20 步路线](./dynaconf-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/dynaconf/`；固定源码当前位置 `/tmp/github-research-dynaconf-0yyqfsyz/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/dynaconf/dynaconf.git <checkout>
git -C <checkout> checkout --detach 32f38478350a80020e7aab60a3cbd29dd7f8d9ea
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[test]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra -m "not integration" tests/ --cov-config pyproject.toml --cov=dynaconf`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。来源纠正证据见official-source-verification.json：最初旧URL实际重定向个人mirror；已保留mirror原始元数据，用真正官方commit API核对同一完整sha及tree 4a018399bfbb635abc4dc956c4a4cf17749ac54e与本地完全相同，origin改官方并复用同Git树基线。没有只换报告URL或把mirror计第二仓。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；许可证保留在原生源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

本轮核心本地测试约43秒，较小库更重；安装体积含大量测试工具，应以实际成本决定后续预算。未跑账号镜像或外部服务，研究完成不代表这些可选后端验收可用。typed目前官方明确技术预览，增强不宣称稳定API承诺；新API仅为工程研究设计。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
