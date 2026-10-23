# 真实项目审查：XlsxWriter

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[jmcnamara/XlsxWriter](https://github.com/jmcnamara/XlsxWriter)。纯Python生成Excel XLSX工作簿，支持格式、公式、表、图表、绘图与打印配置，不依赖Excel进程。
- 固定提交：[5d4606d89a955226d2d0825a0f44309043ae7251](https://github.com/jmcnamara/XlsxWriter/tree/5d4606d89a955226d2d0825a0f44309043ae7251)；版本与运行要求：3.2.9，Python>=3.8。
- 许可证：BSD-2-Clause。实际LICENSE.txt署名John McNamara，源码SPDX与setup.py一致，保留源码/二进制再分发通知。
- 来源确认采用官方 GitHub 仓库、实际 LICENSE 与源码；REST 请求结果（含限流失败）保存在证据目录。issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 3003 个，37,384,391 字节 |
| Python 产品源码 | 42 个文件、26,991 行 |
| Python 测试文件 | 1283 个、81,536 行 |
| 隔离依赖安装 | 6.883 秒，venv 50,149,618 字节 |
| 适用原生基线 | 1787 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 15.027 秒，峰值子进程 RSS 213844 KiB |
| 容器运行 | 整体 15.76 秒，内存 256 MiB、PID 64，无 OOM |

运行无强制第三方依赖；原生CI只安装pytest，本轮采用同命令完整运行。源码跟踪文件约37MB，其中大量真实Excel对照XLSX/图片/文档；这部分成本如实计入，不是只报核心包大小。无需Excel、LibreOffice、数据库或网络。editable构建的xlsxwriter.egg-info已移至本仓证据build-artifacts保留，上游检出git status --porcelain含未跟踪项核对为空；搬移后隔离容器从固定源码导入与完整smoke再验通过。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Workbook管理sheet/Format/Chart与包关系，Worksheet将不同类型写入cell模型/可选常量内存行文件；Format归并到styles，Chart各派生类写OOXML；Packager组装ZIP，Url集中解析链接。读取写入分派、条件格式、链接、表/定义名、autofit/打印与图表分派等相关实现和测试helper；原生comparison用仓库Excel生成参照包解包逐XML比较，不启动Excel。

生成真实inventory.xlsx，含库存表、SUM公式及缓存7、冻结首行和柱状图；独立zipfile/ElementTree解析所有XML/关系部件，并确认B4缓存、chart与table存在。另observations.xlsx实测关闭自动公式后数组字符串仍生公式、条件格式引号未转义、256字符tooltip与定义名/表名仍被接受四类问题，保留完整文件和JSON观察。

## 基线范围与限制

官方python-test.yml同等默认pytest完整集合1787通过、0失败/错误/跳过，无额外-k或目录裁剪。含大量单XML和已有Excel对照工作簿测试。15.027秒，RSS213844KiB，在256MiB/PID64下无OOM。

未用Excel/LibreOffice渲染、重算公式或验证真实交互；ZIP/XML正确及官方参照通过不等于所有Office版本视觉一致。大图表/百万行性能、多Python/PyPy、文档构建未跑。拟议bubble/slicer/customUI等需补充官方OOXML/Excel参照fixture后才能冻结独立验收，当前只是研究路线，未实现接入。

## 迭代路线

[20 步路线](./xlsxwriter-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

4项当前问题修复+16来自实际工作簿/官方需求的增强。已有主题色索引、checkbox、动态数组、autofilter/表、组合图、VBA、普通批注、autofit和常量内存不重新计功能；分别解决其缺口。每步必须观察最终ZIP部件/关系/业务值，不能仅检查方法存在或候选自带测试。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/xlsxwriter/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/jmcnamara/XlsxWriter.git <checkout>
git -C <checkout> checkout --detach 5d4606d89a955226d2d0825a0f44309043ae7251
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run xlsxwriter -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/xlsxwriter/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
