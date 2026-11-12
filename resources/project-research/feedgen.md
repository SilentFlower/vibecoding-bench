# 真实项目审查：feedgen

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[lkiesow/python-feedgen](https://github.com/lkiesow/python-feedgen)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[97260abb1793eb164c458c10b493690beb413f6d](https://github.com/lkiesow/python-feedgen/tree/97260abb1793eb164c458c10b493690beb413f6d)。
- 许可证：BSD-2-Clause OR LGPL-3.0-or-later（本研究按BSD-2-Clause分支核对）。README/setup.py明确二选一双许可，读取license.bsd的两条条件和license.lgpl文本入口；保留Lars Kiesow版权、选择的BSD许可及免责，不把OR误写成必须同时满足两套许可。
- 用途：在本地构建RSS/Atom订阅文档并写出文件，支持作者、日期、正文和可选内容扩展。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 55／252966 |
| 产品 Python 文件／行数 | 17／4213（feedgen/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 18.565 秒，venv 63031393 字节（含本轮测试依赖） |
| 原生基线 | 56 主测试通过、0 失败、0 错误、0 跳过；墙钟 1.359 秒，exit 0 |
| 测试峰值 RSS | 36904 KiB（容器测试进程观测） |

实际运行依赖lxml和python-dateutil，无必需数据库/队列/云凭据。完整基线512MiB预算、RSS36,904KiB，墙钟1.359秒。普通业务另在256MiB离线容器运行，所有示例网址只作为序列化文字，不发请求。

完整默认pytest发现集覆盖feed、entry、演示main及全部上游扩展单元测试，56项通过，终端无警告；未删选。没有执行外部订阅服务、在线聚合器验收、跨Python矩阵或文档构建，这些不称通过。

## 源码与真实场景

读取FeedGenerator与FeedEntry的真实私有数据模型、RSS/Atom构树、日期缺省、entry列表维护、链接/内容/source合同以及ensure_format；source文档和非文本内容分支直接承认尚未支持的范围。第01步固定提交实证：atom_entry把输入link字典变量覆盖成Element，导致rel等元数据未写入；其余为明确增强。内建iTunes/DC/geo/media、多个enclosure、文件写入和演示CLI均已存在，路线没有把它们原样重计。

构建带中文feed标题、研究组作者、明确UTC时间及一条文档记录，分别真实写出/tmp/feed.atom和feed.rss，再由lxml读取；两份文档的条目标题均为第一份文档，RSS说明为完成资料整理。观察同时保存已设置链接字典与实际Atom属性、非文本内容NotImplementedError及其余新增入口缺口。加载/source/feedgen/__init__.py，业务exit0。

完整 [20 步路线](./feedgen-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/feedgen/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/feedgen/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/lkiesow/python-feedgen.git <checkout>
git -C <checkout> checkout --detach 97260abb1793eb164c458c10b493690beb413f6d
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

完整基线命令`<含docker SDK的Python> <evidence>/run_python_baseline.py baseline <evidence> --memory 512m`；业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
