# 真实项目审查：python-docx

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[python-openxml/python-docx](https://github.com/python-openxml/python-docx)。读取、生成和修改Microsoft Word DOCX文件，通过OPC包、WordprocessingML代理提供段落、表、样式、节和批注等能力。
- 固定提交：[e45454602b53e8e572b179ccf1c91093ec9f4ed7](https://github.com/python-openxml/python-docx/tree/e45454602b53e8e572b179ccf1c91093ec9f4ed7)；版本与运行要求：1.2.0，Python>=3.9（旧classifiers仍列3.7/3.8，不作为支持声明）。
- 许可证：MIT。实际LICENSE保留Steve Canny署名；官方GitHub网页与pyproject Repository一致。REST已限流403，保存原响应，不使用宿主GitHub账号或token。
- 来源确认采用官方 GitHub 仓库、实际 LICENSE 与源码；REST 请求结果（含限流失败）保存在证据目录。issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 625 个，54,092,298 字节 |
| Python 产品源码 | 95 个文件、16,081 行 |
| Python 测试文件 | 87 个、15,602 行 |
| 隔离依赖安装 | 4.638 秒，venv 92,507,643 字节 |
| 适用原生基线 | 1609 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 9.376 秒，峰值子进程 RSS 68992 KiB |
| 容器运行 | 整体 9.861 秒，内存 256 MiB、PID 64，无 OOM |

运行lxml>=3.1与typing_extensions>=4.9；本轮上游对应测试依赖behave/pyparsing/pytest/coverage/xdist等独立准备。原生测试在pytest9.1.1私有fixture变化与pyparsing最新弃用警告下不兼容，最终固定声明允许范围内pytest8.4.2、pyparsing3.2.3，未修改测试/关闭warnings=error。源码约54MB含大量真实DOCX/图片参照，依赖与复制成本如实记录。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Document/BlockItemContainer代理段落/表/节；Paragraph/Run/Hyperlink与Comments维护内联结构；样式和编号由parts管理，oxml元素类提供属性，Package按OPC关系图读取/保存ZIP。读取核心文档、表网格/合并、段落运行/超链接、批注创建、核心时间与包关系等实际实现。新版已经支持批注、顺序内容遍历和超链接读取，未将其误列成缺失。

真实report.docx含中文标题、粗体责任人、批注和库存表，保存重开断言数量/格式/表值并独立解析所有XML/关系。另真实改写核心日期输入包复现空日期TypeError；aware日期写入改变瞬间；跨文档run批注产生有commentReference却无comments part的悬挂文件。全部仅用合成文件。

## 基线范围与限制

官方tox的pytest全套1609通过、0失败/错误/跳过；附加原生behave --tags=-wip全套67features/650scenarios通过，1856step只是步骤计数而不加入测试/迭代数量。Behave XML独立保存在bdd-output/junit，由additional_baselines记录650场景。没有-k/文件裁剪；pytest测试命名/警告配置沿pyproject。

依赖准备两轮兼容失败保留pyparsing-preparation与pytest9-preparation，不算产品缺陷或通过证据；最终绿基线使用固定依赖。GitHub REST403保留在repository/issues JSON，源码commit/官方网页/metadata/LICENSE仍可复核。未用Word/LibreOffice渲染、更新域或求实际页数；原生API/XML断言不等于所有Office视觉结果。未跑lint/类型/多Python矩阵，尚未实现20步。

## 迭代路线

[20 步路线](./python-docx-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

3项当前已复现问题修复+17具体文档增强。低层OOXML可手工构造不等于对应公共能力已存在；每个增强均需最终DOCX关系闭合与保存重开验收。字段计算/分页渲染不在编解码库承诺内。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/python-docx/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/python-openxml/python-docx.git <checkout>
git -C <checkout> checkout --detach e45454602b53e8e572b179ccf1c91093ec9f4ed7
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run python-docx -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/python-docx/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。runner使用--pythonpath /src；附加原生命令python -m behave --format progress --tags=-wip --junit --junit-directory=/output/junit。最终测试依赖必须保留pytest8.4.2/pyparsing3.2.3，不覆盖原生警告错误政策。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
