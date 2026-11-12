# 真实项目审查：xmltodict

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[martinblech/xmltodict](https://github.com/martinblech/xmltodict)。单文件 XML ↔ Python dict 交换库，使用 Expat 回调读取、XMLGenerator 写出。
- 固定提交：[6e29fba282e68631034dd2722a413b4e35276584](https://github.com/martinblech/xmltodict/tree/6e29fba282e68631034dd2722a413b4e35276584)；版本与运行要求：1.0.4，Python >=3.9。
- 许可证：MIT。保留 Martin Blech 与 individual contributors 的版权和 MIT 许可。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 22 个，110,896 字节 |
| Python 产品源码 | 1 个文件、657 行 |
| Python 测试文件 | 3 个、1,502 行 |
| 隔离依赖安装 | 9.494 秒，venv 50,155,911 字节 |
| 适用原生基线 | 134 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 1.131 秒，峰值子进程 RSS 40044 KiB |
| 容器运行 | 整体 1.553 秒，内存 256 MiB、PID 64，无 OOM |

核心只用 Python 标准库，无服务或第三方运行依赖；本轮单独安装本地包与 pytest。可选 defusedexpat 仅出现在示例，不是pyproject的必需test extra。本轮未安装该可选解析器，保持默认Expat和默认禁实体规则。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

parse 把文件／字符串／generator送入Expat；_DictSAXHandler维护path、stack、data、item，通过force_list/force_cdata/postprocessor生成普通dict。item_depth闭合时调用callback并释放条目，不把当前已修好的流式累积问题当新缺陷。unparse遍历dict，_emit构造AttributesImpl并递归输出，最小名称校验与注释校验已经存在；默认不承诺混合内容或完整XML词法往返。

真实订单XML读取、force_list规范两条订单后汇总qty=5，写到临时XML文件并重新parse及ElementTree独立解析校验；item_depth=2 callback实际收到两条。另实测空／数字开头名称输出无法独立解析、普通list_iterator输入TypeError、注释特殊字符变化与xml:space默认剔除空白。这些均按现有已声明限制或兼容策略记录为增强，不制造缺陷数量。

## 基线范围与限制

遵循上游tox的原生tests集合完整运行，134通过、0失败／错误／跳过。另试过额外 --doctest-modules，得到134通过/1失败，失败为docstring中import defusedexpat可选依赖缺失；原始 optional-doctest-attempt 目录与JSON保留。最终基线不包含额外示例doctest，不冒称其全过。

20项都是有明确场景的本地增强提案，不代表上游承诺改变“方便dict操作优先于完美XML往返”的取舍。ordered_content、PI、CDATA为opt-in表示模式；XML Name需完整规则设计，不能零散修补。未跑其他Python/PyPy、可选defusedexpat、多平台或文档构建。平台原生入口与冻结新验收未接入。

## 迭代路线

[20 步路线](./xmltodict-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

完整读取了官方现有AGENTS、README相关入口与全部parse/unparse核心。默认实体禁止、注释基本支持、force_cdata选择器、字节解码错误政策、空列表省略与exactly-one-root已存在，全部作为回归，不计新功能。资源预算四个维度合为一个交付，单个场景的测试与重试不拆步。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/xmltodict/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/martinblech/xmltodict.git <checkout>
git -C <checkout> checkout --detach 6e29fba282e68631034dd2722a413b4e35276584
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider tests --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run xmltodict -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/xmltodict/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
