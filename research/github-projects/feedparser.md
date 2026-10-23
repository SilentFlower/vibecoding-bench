# 真实项目审查：feedparser

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[kurtmckee/feedparser](https://github.com/kurtmckee/feedparser)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[a22c5521cbb109871f1a2318948581901bd47e26](https://github.com/kurtmckee/feedparser/tree/a22c5521cbb109871f1a2318948581901bd47e26)。
- 许可证：BSD-2-Clause。LICENSE明确同时覆盖feedparser及单元测试，保留Kurt McKee/Mark Pilgrim版权、两条再分发条件与免责。
- 用途：把本地RSS、Atom和JSON Feed读成统一feed/entries结构，处理日期、编码与内容元数据。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 2362／1472450 |
| 产品 Python 文件／行数 | 33／6854（feedparser/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 13.765 秒，venv 58859253 字节（含本轮测试依赖） |
| 原生基线 | 4,305 主测试通过、0 失败、0 错误、0 跳过；墙钟 14.616 秒，exit 0 |
| 测试峰值 RSS | 99640 KiB（容器测试进程观测） |

运行依赖feedparser-sgmllib和requests，本轮只以本地BytesIO输入运行，不需要服务。原生测试另装responses/pytest-randomly及可选chardet5.2.0，版本与调整来源见requirements-frozen.txt、install-chardet5.json/log。主安装阶段耗时保留installation-result，附加依赖调整未取得总墙钟；不隐藏额外安装。基线512MiB、RSS99,640KiB。

完整默认pytest集合，包括原生JSON、RSS/Atom正常/容错、日期、编码和内容测试，终端无警告。依赖矩阵明确固定可选chardet5.2.0：首次用7.x有6项编码名称/兼容断言失败，日志保存在chardet7-first-*；不称7.x矩阵已通过。按5.2.0准备依赖后完整4,305项全部通过，未删选。未跑跨Python、Sphinx/mypy、打包和可选性能环境。

## 源码与真实场景

读取统一输入流合同、strict/loose解析过程、FeedParserDict的真实键及历史访问器、JSONParser字段映射和日期处理。第01步date_updated/date_modified不一致、第02步content/tags/enclosures未遵循统一结构均实跑保留；第03步清楚标明现有版本表已接受JSON1.1，但数组作者/语言尚未映射，属于补完。现有相对URI处理、日期注册、JSON1.1识别、MediaRSS/iTunes/GeoRSS和流输入不重新计数。其余增强围绕本地订阅数据质量和归档工具。

真实RSS字节包含频道、文档ID、链接、说明及带时区pubDate，解析得到rss20、doc-1和实际UTC日期tuple；另解析中文Atom标题/正文，结果bozo=False。JSON观察分别保存修改日期丢失、内容/分类/附件访问器不一致、多作者/语言丢失及自定义字段未保留。所有输入都是本地字节，加载/source/feedparser/__init__.py，普通业务256MiB上限通过。

完整 [20 步路线](./feedparser-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/feedparser/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/feedparser/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/kurtmckee/feedparser.git <checkout>
git -C <checkout> checkout --detach a22c5521cbb109871f1a2318948581901bd47e26
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

固定chardet5.2.0和其他冻结依赖。完整基线命令`<含docker SDK的Python> <evidence>/run_python_baseline.py baseline <evidence> --memory 512m`；业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
