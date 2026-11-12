# 真实 GitHub 项目审查：markdown-it-py

研究日期：2026-10-21。适合作为保留真实 token 流、规则链和 CommonMark 测试的轻量工程，已复现多个解析/状态问题。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./markdown-it-py-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[executablebooks/markdown-it-py](https://github.com/executablebooks/markdown-it-py)，元数据归档状态为 false。
- 完整固定提交：[6f586542653a56d2ee8549a0dccfaa6ba5ebe14a](https://github.com/executablebooks/markdown-it-py/tree/6f586542653a56d2ee8549a0dccfaa6ba5ebe14a)，包版本 4.2.0。
- 许可证：MIT（含上游 markdown-it 的独立 MIT 归属）。同时保留 LICENSE 与 LICENSE.markdown-it；若复制 CommonMark fixtures，保留其中 CC-BY-SA 4.0 规范归属。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

`MarkdownIt` 配置 preset/options，ParserCore依次规范化、块解析、行内解析和文本合并；块/行内各用Ruler管理规则链。Token保存type/tag/nesting/attrs/map/children/content/meta；SyntaxTreeNode把线性开闭token转为树并可还原；RendererHTML按token渲染。API parse/render/parseInline/renderInline与CLI都是真实入口。已读取类、字段、规则、renderer和适用测试，未把原项目改写成统一app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 181／1340414 |
| 产品源码 | 7480 行 Python，66 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 必需mdurl~=0.1；本轮另装linkify-it-py与testing组对应的pytest/pytest-cov/pytest-regressions/pytest-timeout/requests/flit_core及传递依赖；实际版本冻结，源码未提供统一uv.lock |
| 外部系统 | 完整tests无需服务或凭据；sdist测试仅本地打包，无网络 |
| 安装耗时 | 21.40 秒；受缓存与网络影响 |
| 独立 venv 大小 | 35,255,792 字节，含 pip 和本轮测试工具 |
| 原生基线 | 1032 通过、0 失败、0 错误、0 跳过 |
| 测试进程墙钟／峰值 RSS | 3.36 秒／53,024 KiB |

运行tox.ini原生testenv内部相同的pytest tests命令（专用隔离环境直接执行，未启动tox创建第二环境），完整1,032通过、0失败/错误/跳过，包含CommonMark0.31.2 fixtures、API、CLI、linkify、树与sdist内容。未跑独立mdit-py-plugins仓库套件、benchmark/compare、docs、pre-commit/mypy或多版本矩阵；源码AGENTS推荐的tox包装层未执行。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

真实CLI `python -m markdown_it.cli.parse --enable-tables <临时Markdown>` 读取中文标题和数据表，将stdout写到临时HTML后重新读取检查table。20项观察包含2个有界0.5秒子进程，证明不前进插件规则会卡住；已超时杀死并回收，不让它持续占用。

已在固定原版复现图片alt丢转义/实体、插件规则不消费输入可死循环、未闭合链接污染后续code span、HTML块ASCII/声明规则差异、列表后type-7 HTML边界、冗余空text节点、reset_rules异常不恢复、规则切换消耗一次性iterable、CLI忽略坏UTF-8字节。其余11项是增强。HTML规范判断核对了仓内0.31.2 spec及[官方CommonMark规范](https://spec.commonmark.org/0.31.2/#html-blocks)，不只抄issue结果。

现有line map、Token.as_dict/from_dict、浅copy、SyntaxTreeNode.walk/to_tokens、RendererProtocol、env上下文、规则启停、linkify和preset均保留。line map已存在，新增仅针对缺失的行内精确位置或显式require_map；不把#354旧抽象接口诉求当作仍缺RendererProtocol。当前任务列表/alerts等内置能力不作为新项目特性凑数。

## 二十步路线与接入边界

20项包含9项原版复现修复与11项增强，围绕可见解析正确性、插件出错收口、编辑器定位、多格式渲染和可用CLI。对同一不前进规则的block/inline测试合并为一步，对HTML声明与ASCII匹配合并为一步。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有ProjectVerifier未适配原生token/pytest/CLI，不能以本次成功容器测试称为已接入。本轮内存512MiB/PID128，未验证256MiB默认预算；离线依赖和冻结验收需保持候选包实际加载路径，观察HTML、token语义与磁盘输出。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/markdown-it-py/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/executablebooks/markdown-it-py.git <checkout>
git -C <checkout> checkout --detach 6f586542653a56d2ee8549a0dccfaa6ba5ebe14a
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pytest-cov pytest-regressions pytest-timeout requests flit_core linkify-it-py
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run markdown-it-py baseline -- \
  -m pytest tests -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run markdown-it-py observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
