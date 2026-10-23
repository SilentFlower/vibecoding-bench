# 真实项目审查：JMESPath.py

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[jmespath/jmespath.py](https://github.com/jmespath/jmespath.py)。JSON查询语言的Python实现，包括词法分析、Pratt解析、AST求值、标准/自定义函数和jp.py命令行。
- 固定提交：[2812594e69d43098ef60f81f4efc404c071b0418](https://github.com/jmespath/jmespath.py/tree/2812594e69d43098ef60f81f4efc404c071b0418)；版本与运行要求：1.1.0，Python>=3.9。
- 许可证：MIT。实际LICENSE署名Amazon.com, Inc. or affiliates；setup.py官方URL与GitHub元数据一致。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 62 个，274,352 字节 |
| Python 产品源码 | 9 个文件、1,729 行 |
| Python 测试文件 | 7 个、849 行 |
| 隔离依赖安装 | 7.702 秒，venv 50,152,557 字节 |
| 适用原生基线 | 991 通过、0 失败、0 错误、1 跳过 |
| 基线进程 | 1.858 秒，峰值子进程 RSS 38912 KiB |
| 容器运行 | 整体 2.223 秒，内存 256 MiB、PID 64，无 OOM |

运行无第三方依赖；上游tox命令python -m pytest tests，测试合规JSON固定在仓库，不需子模块下载。此次pytest精确版本见冻结依赖；requirements.txt有另一套开发版本约束，本轮遵循tox未固定pytest的原生命令，记录当前pytest弃用警告。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Lexer产生type/value/start/end，Parser使用Pratt规则生成字典AST并全局缓存ParsedResult；TreeInterpreter遍历AST，Options绑定dict_cls和custom_functions；Functions通过装饰器签名与元类注册函数，expref可对集合元素延迟求值。读取了词法、缓存/ParsedResult、各访问器、函数校验/集合函数、exceptions与CLI全部相关契约；原生compliance测试逐条读取仓库JSON并区分语法/类型/值/参数数量错误。

对三条库存记录按qty过滤、映射code/stock并按stock排序，真实jp.py子进程的标准输出独立JSON解析后与库编译查询结果一致，并保存projection.json。当前提交复现容器布尔/数字错误相等、变参后续类型漏校验、可变字面量污染缓存、token绝对偏移错误、混合类型比较TypeError五项；CLI空表达式Traceback是新增诊断政策的观察。

## 基线范围与限制

上游tox的tests完整集合991通过、1跳过、0失败/错误、24警告；唯一跳过为Python2 long类型专属。覆盖当前tests/compliance及legacy文件，未设置JMESPATH_TEST做范围裁剪；bench标记fixture由上游生成器按设计不作普通测试。

24警告由22条旧字面量PendingDeprecationWarning和2条pytest参数生成器弃用构成；未跑多Python/PyPy矩阵、性能bench、lint或静态类型。JSON语言限定JSON类型，不将任意Python对象/修改文档作为20步配额；三个业务函数都为显式可选扩展，不冒称标准已经支持。

## 迭代路线

[20 步路线](./jmespath-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

5项当前问题修复+15增强，围绕语言一致性、可复用查询服务、诊断/预算和CLI真实工作流。已有compile、Parser.purge、多选hash、dict_cls、自定义函数和标准map/sort_by不重算新增功能；不以增加测试数量拆分迭代。官方规范用于核对类型与比较契约：https://jmespath.org/specification.html；所有拟议接口尚未实现。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/jmespath/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/jmespath/jmespath.py.git <checkout>
git -C <checkout> checkout --detach 2812594e69d43098ef60f81f4efc404c071b0418
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run jmespath -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/jmespath/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
