# 真实项目审查：cssselect

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[scrapy/cssselect](https://github.com/scrapy/cssselect)；官方网站／项目元数据与 GitHub commit API 已交叉核对，原始内容见 repository.json、commit.json。
- 完整提交：[3069b6da75e1adf27939ca541dcc9fb9b961abc6](https://github.com/scrapy/cssselect/tree/3069b6da75e1adf27939ca541dcc9fb9b961abc6)。
- 许可证：BSD-3-Clause。已读取 LICENSE 的三条再分发条件及 AUTHORS；GitHub API 的 NOASSERTION 以源码许可证和 pyproject.toml 的 BSD-3-Clause 为准。未来分发保留版权、条件、免责及归属，且不以作者名背书。
- 用途：把 CSS 选择器解析为树并转换成 XPath 1.0，用于本地 XML/HTML 文档查询。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 27／234209 |
| 产品 Python 文件／行数 | 3／2282（cssselect/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512MiB 上限运行 |
| 安装 | 16.126 秒，venv 64116364 字节（含本轮测试依赖） |
| 原生基线 | 34 主测试通过、76 子测试通过；0 失败、0 错误、0 跳过（JUnit通过聚合110）；墙钟 1.506 秒，exit 0 |
| 测试峰值 RSS | 61668 KiB（容器测试进程观测） |

产品无服务、云凭据或数据库需求。lxml 只用于原生测试和本轮真实 XPath 求值；产品转换功能本身无该运行依赖。安装依赖有 lxml、pytest、pytest-cov、Sybil，版本和下载来源见安装清单；测试在已准备依赖的离线容器运行。

完整执行上游 tox 的适用运行集合 cssselect tests docs（pytest+Sybil），未删选测试。未运行上游独立 typing、pylint、pre-commit、Sphinx HTML 构建和发行包检查；这些不计入运行集合通过。原生基线实际命令：pytest -q -ra -p no:cacheprovider --junitxml=/tmp/results.xml cssselect tests docs。

## 源码与真实场景

实际阅读了 Selector 与各树节点、parse 的三个快速路径、TokenStream/tokenize、not/is/where/has 的分支解析，及 GenericTranslator.css_to_xpath/selector_to_xpath、反向组合符条件、HTMLTranslator 的 lang/link/表单状态实现。parser.py 负责 grammar、canonical 与 specificity；xpath.py 负责 XPath1 生成；公开包仅导出 parse、树入口、异常和两个 translator。tests/test_cssselect.py 覆盖 token、解析、翻译及 lxml 实际求值；docs/conftest.py 通过 Sybil 执行文档示例。文档明确承认多项 Level4 限制，路线中的这些条目均标为增强，而非声称原版违反了承诺。

observe.py 确认实际加载 /source/cssselect/__init__.py，并在 lxml XML 上执行 p.active、p:not(.active)、main:has(> p.active)、ASCII 不区分大小写属性选择器，结果分别为 a、b、main、c。逐项记录 11 个未支持选择器错误和其余公开入口缺失；缺少 API 只证明需要增强，不能作为缺陷复现或已实现目标。

完整 [20 步路线](./cssselect-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/cssselect/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/cssselect/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/scrapy/cssselect.git <checkout>
git -C <checkout> checkout --detach 3069b6da75e1adf27939ca541dcc9fb9b961abc6
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

取证环境的宿主 Python 额外需要 docker SDK。先按锁定依赖安装，再使用本目录 run_python_baseline.py baseline <evidence> --memory 512m --tests cssselect tests docs；业务观察由 run_python_probe.py <evidence> 执行。证据脚本需要本机 Docker 和记录的账号镜像；不挂载账号私有目录。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

本研究只处理普通文本／文档功能。未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
