# 真实 GitHub 项目审查：Mistune

研究日期：2026-10-21。适合作为纯 Python Markdown 解析、插件和多格式渲染工程；原生功能广，迭代重点是可观测解析与文档生产能力。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./mistune-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[lepture/mistune](https://github.com/lepture/mistune)，元数据归档状态为 false。
- 完整固定提交：[4bbaa04c391d650a2e1219781c9a9acd60571cce](https://github.com/lepture/mistune/tree/4bbaa04c391d650a2e1219781c9a9acd60571cce)，包版本 3.4.0。
- 许可证：BSD-3-Clause。必须保留 LICENSE 的版权、许可条件和免责声明，不能用维护者名称暗示背书。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

`create_markdown()` 构建 Markdown、BlockParser、InlineParser 和 renderer；块解析保存引用定义，渲染阶段展开行内 token，前后 hooks 提供扩展。HTMLRenderer 处理 HTML 与 URL 协议，MarkdownRenderer／RSTRenderer 生成源文本；插件提供表格、脚注、数学等；RSTDirective／FencedDirective 组合本地 include 与其他指令。CLI `python -m mistune` 接受消息、文件或 stdin。已实际读取这些类及方法，不重写成 app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 148／881478 |
| 产品源码 | 6419 行 Python，39 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 核心无第三方运行依赖；本轮另装 pytest、pytest-cov 及其传递依赖，精确版本在 requirements-frozen.txt；未按 uv.lock 安装整个 lint/docs 组 |
| 外部系统 | 基线和场景无需外部服务、系统包或凭据 |
| 安装耗时 | 14.54 秒；受缓存与网络影响 |
| 独立 venv 大小 | 28,258,423 字节，含 pip 和本轮测试工具 |
| 原生基线 | 1324 主测试通过、158 子测试通过、0 失败、0 错误、0 跳过 |
| 测试进程墙钟／峰值 RSS | 7.77 秒／92,892 KiB |

运行上游 pyproject.toml 配置的完整 tests 集合，1,324 个主测试和158个子测试通过，JUnit记录共1,482项，无跳过；filterwarnings=error 生效。覆盖 CommonMark fixtures、安全边界、插件、渲染器和性能回归。未跑 ruff、mypy、Sphinx 构建、覆盖率上报或多 Python 矩阵。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；两个临时容器都已删除并核对不存在，无 OOM。

实际通过 table 插件渲染含中文标题和数据的 Markdown，将完整 HTML 写入临时文件并重新读回核对 `<table>`；临时目录自动删除。20 条原版观察分别调用 CLI／原生 parser、renderer 和 include，全部输出留存。

已复现空 stdin 被判为缺少输入、CLI 选择 ast 后 AssertionError、同一脚注多次引用产生重复 HTML id。其余 17 项为已核对的增强缺口：例如 token 无源位置、HTML 回调不接收 state、AST 模式使用 TOC hook 会断言、RST 表格及 Markdown 脚注缺 renderer、include 忽略行范围。未把公开 issue #461 的任意导入直接宣布为漏洞；插件由可信代码配置是现有扩展机制，路线只提供可选内置插件策略。

已存在的安全 URL 策略、默认 HTML 转义、脚注、任务列表、数学、表格及列表／引用中的显式插件、include 路径／循环保护、可自定义 heading_id、可子类化 renderer 都作为回归，不计新增。旧 issue 的标题换行或未知 HTML 标签行为没有直接当作缺陷；CommonMark 允许的规范化不要求字节保真。

## 二十步路线与接入边界

20 步为 2 项已复现修复、18 项增强，包含 CLI AST 输出、源位置、上下文渲染、纯文本、跨格式插件、TOC、脚注合成、诊断、元数据、围栏属性、include 能力和批处理。每项有独立用户效果和实际原版观察。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有 ProjectVerifier 仍不支持这套原生 pytest／CLI 协议；本次用 512 MiB／PID 128 测全套，不宣称默认 256 MiB／PID 64 已验证。应保留真实 src 布局并先准备离线依赖，冻结用例按候选 HTML／AST／文件副作用验收。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/mistune/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/lepture/mistune.git <checkout>
git -C <checkout> checkout --detach 4bbaa04c391d650a2e1219781c9a9acd60571cce
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pytest-cov
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mistune baseline -- \
  -m pytest -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mistune observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
