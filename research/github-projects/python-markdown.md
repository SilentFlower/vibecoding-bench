# 真实 GitHub 项目审查：Python-Markdown

研究日期：2026-10-21。适合无服务依赖的文本解析工程，重点是扩展互操作、文件接口与文档生产，而非宣称它已经完全兼容 CommonMark。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./python-markdown-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[Python-Markdown/markdown](https://github.com/Python-Markdown/markdown)，元数据归档状态为 false。
- 完整固定提交：[b41e0aaf1181f1a8cb200cf5a815aad7c0020d23](https://github.com/Python-Markdown/markdown/tree/b41e0aaf1181f1a8cb200cf5a815aad7c0020d23)，包版本 3.11.2。
- 许可证：BSD-3-Clause。保留 LICENSE.md 和各源文件的原始版权与免责声明。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

`Markdown` 构建 preprocessors、BlockParser、inlinePatterns、treeprocessors、postprocessors 五段流水线；中间表示为 ElementTree，序列化后恢复 HTML stash。内置扩展通过 Extension 与优先级 Registry 注册，支持 TOC、footnotes、meta、tables、admonition、attr_list、fenced_code、CodeHilite、wikilinks。`convert` 返回HTML，`convertFile`读写文件/二进制流，CLI为`python -m markdown`／markdown_py。已读取相关定义与测试；真实工程保持独立结构。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 473／2519780 |
| 产品源码 | 8877 行 Python，33 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 核心无第三方运行依赖；本轮装 PyYAML、Pygments、pytest、unittest-xml-reporting（含lxml）。实际版本冻结在requirements-frozen.txt，未声称使用整个uv.lock开发环境 |
| 外部系统 | 不需要数据库服务、云凭据或额外系统包；未安装pytidylib/libtidy |
| 安装耗时 | 9.40 秒；受缓存与网络影响 |
| 独立 venv 大小 | 42,176,751 字节，含 pip 和本轮测试工具 |
| 原生基线 | 1019 通过、0 失败、0 错误、110 跳过 |
| 测试进程墙钟／峰值 RSS | 2.73 秒／33,664 KiB |

最终使用上游 unittest discover 的完整 tests，XMLTestRunner仅记录JUnit：1,019通过、110跳过、0失败/错误。跳过原因为59项要求特定Pygments版本环境（本轮未启用上游2.7.1矩阵）、39项缺Tidylib、8项上游Excluded、2项上游标注已知broken、2项上游固定宽松列表差异。初次直接pytest因上游warnings=error与pytest收集TestSuite的警告冲突中断，保留pytest-attempt-*，随后按原生unittest成功运行；这不是修复产品。未跑lint/docs/拼写/链接检查或多版本矩阵。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

实际调用`python -m markdown -x toc -f <临时HTML> <临时Markdown>`，读取落盘HTML核对带id的中文h1；原生API同时覆盖20项观察。临时文件均自动删除。

原版复现四个交付问题：含code span的折叠引用不能解析、admonition内原始HTML被错误包进段落、CLI静默忽略额外输入文件、官方支持的类级Extension.config在实例间串值。其余16项增强明确为试点方案。新观察确认HTML模式的download裸属性输出已存在，因此不采用旧issue #1501的表面描述；脚注定义/文档顺序配置和Unicode slug函数也已存在，均排除。

保留既有HTML/XHTML、裸布尔属性、meta扁平文本、TOC层级/Unicode自定义slug、脚注多引用回链及UNIQUE_IDS/USE_DEFINITION_ORDER、fenced_code属性和高亮、Registry扩展机制作为回归。Python-Markdown明确不清洗不可信HTML，本路线不把它包装成HTML sanitizer，也不将与CommonMark的所有差异认定BUG。第三方pymdown-extensions可解决部分功能，但本仓尚未提供这些原生可选能力，路线应说明采用内置实现与外部扩展的取舍。

## 二十步路线与接入边界

20项为4项复现修复、16项增强，跨引用、HTML嵌套、CLI、配置隔离、TOC、表格、围栏、高亮、Wiki、元数据与文件API，每项有实际观察和独立用户收益。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有verifier仍只接app.py/JSON行；本轮512MiB/PID128原生隔离不代表默认256MiB预算已验证。后续须保留真实Markdown包、准备固定离线依赖，冻结用例实际检查HTML结构、API结果和文件字节。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/python-markdown/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/Python-Markdown/markdown.git <checkout>
git -C <checkout> checkout --detach b41e0aaf1181f1a8cb200cf5a815aad7c0020d23
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pyyaml pygments unittest-xml-reporting
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run python-markdown baseline -- \
  /evidence/native_unittest.py
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run python-markdown observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
