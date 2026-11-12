# 真实项目审查：python-pptx

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[scanny/python-pptx](https://github.com/scanny/python-pptx)。创建、读取和更新PowerPoint PPTX文件，支持形状、表格、图表、媒体、主题布局与备注。
- 固定提交：[278b47b1dedd5b46ee84c286e77cdfb0bf4594be](https://github.com/scanny/python-pptx/tree/278b47b1dedd5b46ee84c286e77cdfb0bf4594be)；版本与运行要求：1.0.2，Python>=3.8。
- 许可证：MIT。实际LICENSE保留Steve Canny署名；分工别名python-openxml/python-pptx为404，官方GitHub及pyproject Repository均为scanny/python-pptx，仅此canonical计数。REST403保留，未使用宿主token。
- 来源确认采用官方 GitHub 仓库、实际 LICENSE 与源码；REST 请求结果（含限流失败）保存在证据目录。issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 798 个，63,184,295 字节 |
| Python 产品源码 | 101 个文件、27,830 行 |
| Python 测试文件 | 83 个、25,255 行 |
| 隔离依赖安装 | 4.718 秒，venv 129,189,780 字节 |
| 适用原生基线 | 2700 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 13.111 秒，峰值子进程 RSS 94152 KiB |
| 容器运行 | 整体 13.643 秒，内存 256 MiB、PID 64，无 OOM |

运行Pillow>=3.3.2、XlsxWriter>=0.5.7、lxml>=3.1与typing_extensions>=4.9；测试另外behave/pyparsing/pytest/coverage/xdist等。与docx相同，固定声明允许的pyparsing3.2.3和pytest8.4.2以解决最新测试依赖兼容，未改测试或关闭warnings=error。固定源码约63MB，包含真实PPTX/图像/规格资料，不能只按核心模块声称极小。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Presentation/Slides关联SlidePart及布局母版，ShapeTree管理形状ID/几何/关系，Table与TextFrame代理DrawingML；图表数据经Chart XMLwriter生成图表并用XlsxWriter内嵌工作簿，OPC package按关系图读写ZIP。已读Slides/Presentation、shape tree/图表创建、notes/table/text/base shape、颜色值对象和OPC图遍历等契约。现有movie、group、notes、表格merge和多plot读模型不被误当新增。

真实inventory.pptx含中文标题、库存表、柱状图和备注，保存重开断言单元格/图表值/notes，并独立解析所有XML/关系，确认chart与嵌入XLSX存在。RGBColor.from_string的5/7位hex均被接受并转换为另一颜色，已保存观察；合法6位作通过对照。

## 基线范围与限制

官方tox的pytest默认完整集合2700通过、0失败/错误/跳过；附加behave --tags=-wip完整54features/973scenarios通过，2914step只是BDD步骤不并入通过项或迭代数。独立XML在bdd-output/junit，additional_baselines记973场景；未裁剪测试。

首次pyparsing最新版本弃用警告导致收集错误，第二轮pytest9私有fixture finalizer变化导致16错误；准备失败分别保留，最终固定依赖全绿，不计产品BUG。REST403由官方网页/实际git/pyproject/LICENSE交叉补证，原响应不伪造成成功。未启动PowerPoint/LibreOffice渲染、动画播放或计算页内排版；真实ZIP/重开与原生套件不能代替视觉交互验收。未跑多Python/类型/lint或大文件性能。

## 迭代路线

[20 步路线](./python-pptx-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

1项当前颜色问题修复+19个PPTX实际编辑/生成增强；不为凑BUG改写现有底层能力。复制、动画、组合图、母版导入等有真实关系依赖，因此先交基础关系管理，再交联动能力；每步都需实际PPTX副作用、重开和此前回归，不以方法存在验收。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/python-pptx/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/scanny/python-pptx.git <checkout>
git -C <checkout> checkout --detach 278b47b1dedd5b46ee84c286e77cdfb0bf4594be
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run python-pptx -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/python-pptx/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。runner须--pythonpath /src；附加原生命令python -m behave --format progress --tags=-wip --junit --junit-directory=/output/junit。完整测试依赖锁保留pytest8.4.2/pyparsing3.2.3。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
