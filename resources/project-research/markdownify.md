# 真实项目审查：markdownify

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[matthewwithanm/python-markdownify](https://github.com/matthewwithanm/python-markdownify)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[bc98c9e134ec55b2853716ab859754f061cb7054](https://github.com/matthewwithanm/python-markdownify/tree/bc98c9e134ec55b2853716ab859754f061cb7054)。
- 许可证：MIT。读取LICENSE及源码项目URLs，保留Matthew Tretter版权、MIT许可与免责；BeautifulSoup和six为独立依赖按各自元数据冻结。
- 用途：以BeautifulSoup DOM为基础将本地HTML转换成Markdown，支持子类覆盖各标签转换。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 24／94352 |
| 产品 Python 文件／行数 | 2／878（markdownify/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 22.23 秒，venv 51702877 字节（含本轮测试依赖） |
| 原生基线 | 83 主测试通过、0 失败、0 错误、0 跳过；墙钟 1.97 秒，exit 0 |
| 测试峰值 RSS | 39424 KiB（容器测试进程观测） |

运行依赖beautifulsoup4>=4.9,<5及six>=1.15,<2，默认html.parser无需浏览器或外部服务；本轮依赖版本见冻结清单。完整基线512MiB预算、RSS39,424KiB；普通业务另在256MiB离线容器执行。

完整默认pytest集合，83项通过，未删选；终端无警告。未执行tox中的flake8、README restructuredtext-lint或不同Python版本矩阵；未宣称这些检查通过。

## 源码与真实场景

读取MarkdownConverter选项合并、DOM遍历/空白边界、函数分派缓存、parent_tags上下文、convert_a/code/pre/li/tr与CLI参数映射。源码已有动态行内反引号、代码语言callback、colspan、caption/figcaption、video、定义列表与Soup入口，路线均没有把这些已有能力重计。第01步由API/CLI真实默认差异取证，第02步来自convert_dt的明确TODO和输出，第03步是pre固定围栏碰撞，第04步是资源目的地/属性文字拼接边界；其余是明确增强。

真实中文资料清单HTML含标题、强调、相对指南链接、从3开始的列表和两列表格，原生ATX输出保留全部业务字段；观察脚本同时运行真正的python -m markdownify.main默认入口，与API对照。原输出中的Markdown语法保存在JSON/log而非报告中渲染成真实本地链接。加载/source/markdownify/__init__.py，业务exit0。

完整 [20 步路线](./markdownify-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/markdownify/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/markdownify/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/matthewwithanm/python-markdownify.git <checkout>
git -C <checkout> checkout --detach bc98c9e134ec55b2853716ab859754f061cb7054
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
