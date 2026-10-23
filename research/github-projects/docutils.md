# 真实 GitHub 项目审查：Docutils

研究日期：2026-10-21。运行成本适合原生文档转换研究；源码约4.7万行，范围比首批小库更大，本轮仅正式docutils包，镜像sandbox/web不作为seed。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./docutils-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方文档列出的GitHub镜像：[live-clones/docutils](https://github.com/live-clones/docutils)，元数据归档状态为 false。
- 完整固定提交：[3577cb69446ed0c94c15f9b0836571d6d5c46882](https://github.com/live-clones/docutils/tree/3577cb69446ed0c94c15f9b0836571d6d5c46882)，包版本 1.0b1.dev。
- 许可证：正式docutils模块以Public Domain为主，COPYING.rst列出BSD-2-Clause/BSD-3-Clause及Emacs工具GPL-3.0-or-later例外。已读COPYING.rst及其列出的随附licenses目录：正式包归属与例外有明确清单；保留源码头/声明和全部适用许可。Emacs工具独立GPL例外须保留相应文本。sandbox明示不属于发行包，本轮不将它混入seed或称其都适用主许可。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

原始项目使用SourceForge SVN，GitHub [readthedocs/docutils](https://github.com/readthedocs/docutils)查询404，未误用同名旧fork；选择[官方仓库说明](https://docutils.sourceforge.io/docs/dev/repository.html)明确指向的第三方镜像live-clones/docutils，并冻结完整Git commit。正式包位于source/docutils/，core.Publisher依次组合reader/parser/transforms/writer与io，RST状态机建立nodes文档树，HTML5/LaTeX/ODT等Writer输出结果，API为publish_doctree/publish_parts/publish_string，CLI为python -m docutils。GitHub镜像不是上游canonical，问题跟踪在SourceForge；issues.json为空因镜像关闭issue。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 2970／26492930 |
| 产品源码 | 47009 行 Python，128 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 核心无强制第三方运行依赖；本轮预装pytest、Pygments、Pillow、unittest-xml-reporting及其依赖。实际版本冻结，Docutils本身没有本轮统一锁文件；安装目标为source/docutils/子目录，不是仓根 |
| 外部系统 | HTML/AST/ODT等原生测试无需服务或凭据；未安装外部TeX/MathML转换程序或可选Markdown parser |
| 安装耗时 | 14.45 秒；受缓存与网络影响 |
| 独立 venv 大小 | 64,333,204 字节，含 pip 和本轮测试工具 |
| 原生基线 | 456 通过、0 失败、0 错误、3 跳过 |
| 测试进程墙钟／峰值 RSS | 6.46 秒／62,440 KiB |

按上游alltests.py同样的unittest discover，在source/docutils/test工作目录运行，XML仅统计测试方法：456通过、3跳过、0失败/错误，另记录1,775个内部subTest全部通过，不能把两种计数混为同一指标。跳过为缺可选Markdown parser、上游规定外部数学转换器须stand-alone运行、特定syntax-highlight条件。为补齐subTest计数曾重复一次同套基线；最终计数在baseline-output/subtest-counts.json。未跑Emacs、sandbox、外部转换器、lint/docs或多Python矩阵。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

原生CLI使用html5 writer转换含中文标题和list-table的临时RST，写入HTML文件并重新读回核对table；按新版CLI显式-o指定输出。原生API观察20个独立目标，文件访问示例只读同一临时目录内的合成outside.txt，没有访问任何业务或账号数据。

实际复现未知writer错误仍退出0；其余19项为源码与真实转换核对的增强提案。多数来自[官方To Do](https://docutils.sourceforge.io/docs/dev/todo.html)，并结合当前选项、writer查找和HTML/树输出确认：限制文件访问、严格配置/语言、页脚本地化、稳定ID、对象编号、分册/分页面、嵌套行内、URI注册、分段列表、Unicode表格、表格列样式、片段提取、新writer、代码标题和可折叠提示。未仅凭旧todo宣布这些都已是BUG。

已存在的include行范围/encoding/依赖文件列表、root_prefix路径重映射、文件插入总开关、raw总开关、HTML5图像加载策略、图表caption、TOC/节编号、自链接、MathML、代码行号、高亮、XML/pseudoxml/ODT writer和可选CommonMark wrapper均不计新增。文件插入允许行为是既有规则；root_prefix不是访问沙箱。Sphinx可处理大型文档和交叉引用，路线明确是Docutils原生可选能力，不暗称上游本来保证这些能力。

## 二十步路线与接入边界

20项为1项已复现CLI修复、19项独立增强。大型能力各限定MVP，不把同一能力的测试/文档拆成多步；章节打包、分页面、格式writer和对象编号解决不同的交付效果。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有verifier尚未适配Docutils的真实子目录包与CLI/文件输出。应固定镜像提交和正式包子树、预备离线依赖，候选PYTHONPATH优先/tmp/source/docutils；本轮已核对source_module实际为该源码。512MiB/PID128隔离通过不等于默认256MiB/PID64预算或生产接入已完成。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/docutils/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/live-clones/docutils.git <checkout>
git -C <checkout> checkout --detach 3577cb69446ed0c94c15f9b0836571d6d5c46882
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout>/docutils pytest pygments pillow unittest-xml-reporting
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run docutils baseline -- \
  /evidence/native_unittest.py
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run docutils observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
