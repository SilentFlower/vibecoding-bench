# 真实项目审查：dpath

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[dpath-maintainers/dpath-python](https://github.com/dpath-maintainers/dpath-python)。通过分段路径和文件名式glob检索、创建、修改、删除嵌套Python字典/列表，并提供深合并。
- 固定提交：[15759d96a006fef5278de731cd263b4d839094c3](https://github.com/dpath-maintainers/dpath-python/tree/15759d96a006fef5278de731cd263b4d839094c3)；版本与运行要求：2.2.0，Python>=3.7。
- 许可证：MIT。实际LICENSE.txt保留Andrew Kesterson与Caleb Case署名。原分工别名dpath-maintainers/dpath为404；setup.py和官方仓库共同指向dpath-maintainers/dpath-python，仅此身份计数。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 34 个，98,477 字节 |
| Python 产品源码 | 7 个文件、938 行 |
| Python 测试文件 | 14 个、1,562 行 |
| 隔离依赖安装 | 7.824 秒，venv 57,875,960 字节 |
| 适用原生基线 | 79 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 19.688 秒，峰值子进程 RSS 246400 KiB |
| 容器运行 | 整体 20.087 秒，内存 256 MiB、PID 64，无 OOM |

运行时无第三方依赖；上游tox.ini使用nose2与Hypothesis，本轮完整安装并用原生nose2执行，另有取证通用pytest但未以其替代原生集合。精确依赖及venv成本见requirements-frozen.txt和安装JSON。无需服务、数据库或网络。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

公开new/set/delete/get/search/values/merge在dpath/__init__.py；segments.py负责路径遍历、fnmatch匹配、类型提示与原地set；types.py定义PathSegment、ListIndex和MergeType；options.py目前只有全局空字符串键开关。已读取核心函数全部实现、路径段/列表索引定义及对应测试，区分new字面量创建和set只改已有键等原生契约。

将两台服务器的port通过通配更新为8080，创建team标签，深合并region；写config.json并由标准json独立读回。另复现过滤删除越界与整数键merge TypeError两项问题；路径字符串信息损失、循环递归、TYPESAFE部分更新与文档注明的源引用共享只记为增强观察。

## 基线范围与限制

上游tox的nose2原生集合79项全部通过，0失败/错误/跳过；其中Hypothesis属性测试含多轮生成示例，不能把生成次数当作独立迭代或测试项。JUnit由nose2官方插件输出，没有裁剪文件或用例。

Hypothesis随机生成使耗时/峰值随运行变化；本次RSS246400KiB，接近256MiB预算，不能据单次无OOM保证所有随机种子成本。nose2 JUnit插件在Python3.12产生utcfromtimestamp弃用警告，保留原日志；未运行多Python tox矩阵/文档构建。只对两项当前提交确定复现的问题称BUG，其余均为拟议增强。

## 迭代路线

[20 步路线](./dpath-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

2项问题修复+18项按配置编辑/合并实际需求提出的增强。已有分段路径、负索引查询、afilter、列表占位、creator、ADDITIVE/REPLACE/TYPESAFE不重新计作新功能；新增接口名称是待实现契约。原子编辑、按路径列表策略、按业务键对齐及冲突解析分别解决不同交付需求，不把测试/修复重试单独计步。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/dpath/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/dpath-maintainers/dpath-python.git <checkout>
git -C <checkout> checkout --detach 15759d96a006fef5278de731cd263b4d839094c3
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m nose2 --no-user-config --plugin nose2.plugins.junitxml --junit-xml --junit-xml-path /output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run dpath -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/dpath/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
