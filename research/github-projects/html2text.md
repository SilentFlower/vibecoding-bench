# 真实项目审查：html2text

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[Alir3z4/html2text](https://github.com/Alir3z4/html2text)；官方网站／项目元数据与 GitHub commit API 已交叉核对，原始内容见 repository.json、commit.json。
- 完整提交：[5cf85510a2498546d5b48ad1bf7d75b146aac591](https://github.com/Alir3z4/html2text/tree/5cf85510a2498546d5b48ad1bf7d75b146aac591)。
- 许可证：GPL-3.0-or-later。源码 COPYING 为GPLv3全文，pyproject.toml明确GPL-3.0-or-later，README保留Aaron Swartz归属。只做本地研究；以后分发原版或修改版须按GPL保留版权、许可、对应源码及相应声明，不能仅标成宽松许可。
- 用途：把本地HTML转换为便于阅读的Markdown结构化文本，不渲染网页或访问网络。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 180／203326 |
| 产品 Python 文件／行数 | 8／1904（html2text/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512MiB 上限运行 |
| 安装 | 13.148 秒，venv 51860712 字节（含本轮测试依赖） |
| 原生基线 | 196 通过、0 失败、0 错误、0 跳过；墙钟 6.224 秒，exit 0 |
| 测试峰值 RSS | 32920 KiB（容器测试进程观测） |

转换本身只有Python标准库，无服务器、数据库、浏览器或云凭据。测试依赖pytest/pytest-cov已固定版本，完整基线在512MiB离线容器内完成，峰值约32MiB。

原生终端另有3条pytest参数生成器弃用警告，未将警告当失败或隐藏。完整执行默认pytest发现集，与tox运行范围一致；包括模块/API/CLI快照用例与内存/多次调用回归，无删选。未运行Black、flake8、isort、mypy和多Python版本矩阵；未把这些称为通过。

## 源码与真实场景

读取HTML2Text的构造选项、handle/finish生命周期、标签分派、锚点引用、ListElement计数、table输出、代码块与换行包装；AnchorElement仅保存链接属性和引用编号，ListElement保存列表种类/计数。cli.py读取本地文件或stdin并逐项映射配置，原生测试涵盖模块、命令与便利函数三条入口。现有backquote_code_style、ol start、tag_callback、image模式和sup/sub能力均已存在，路线没有把它们重新计作新功能，而逐项定义尚缺的能力与兼容范围。

真实周报HTML包含中文标题、强调、相对链接、两项清单和表格，原生API输出包含`# 周报`、`**文档整理**`、`[指南](guide.md)`及表格业务值。observe.py另逐项执行17组普通HTML边界，并核对来源映射/严格配置/分块接口缺失。原版反引号代码、列表跳号/反向、合并单元格及注音输出均原样保留，不把增强目标声称成已通过。加载/source/html2text/__init__.py，场景exit0。

完整 [20 步路线](./html2text-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/html2text/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/html2text/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/Alir3z4/html2text.git <checkout>
git -C <checkout> checkout --detach 5cf85510a2498546d5b48ad1bf7d75b146aac591
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

先按test-requirements.txt安装固定依赖并editable安装固定源码；完整基线命令`<含docker SDK的Python> <evidence>/run_python_baseline.py baseline <evidence> --memory 512m`；业务观察命令`<同一Python> <evidence>/run_python_probe.py <evidence>`。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

本研究只处理普通文本／文档功能。未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
