# 真实 GitHub 项目审查：mdit-py-plugins

研究日期：2026-10-21。适合真实插件集合的累计工程；以插件注册、父块边界、属性契约和组合渲染为主，不将不同格式参数当成独立项目。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./mdit-py-plugins-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[executablebooks/mdit-py-plugins](https://github.com/executablebooks/mdit-py-plugins)，元数据归档状态为 false。
- 完整固定提交：[519953da0a394a92534bc27580f4e7415462df44](https://github.com/executablebooks/mdit-py-plugins/tree/519953da0a394a92534bc27580f4e7415462df44)，包版本 0.7.0。
- 许可证：项目MIT，保留各移植插件附带的原MIT声明；tasklists内嵌原ISC许可；GFM/CommonMark规范派生示例另保留CC BY-SA 4.0归属。已读取front_matter/footnote/admon/container/deflist/texmath各LICENSE与tasklists的完整ISC声明；attrs/parse.py注明改编自Djot固定fae7364b86bfce69bc6d5b5eede1f5196d845fd6，另保存该提交John MacFarlane MIT原文。GFM官方规范页明示基于CommonMark并采用CC BY-SA 4.0，保存官方页及许可文本，不把规范示例改标为项目MIT。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

每个插件接收真实MarkdownIt并注册block/inline/core rule及render rule。dollarmath/texmath操作StateBlock/StateInline位置、父块和map；attrs使用状态机解析并将属性加到对应Token；tasklists修改inline子树；anchors遍历标题分配slug；footnote通过env累积引用并移到尾部；front_matter产生hidden Token；container/admon包装嵌套块。新GFM组合/自动链接需要核心4.1接口。已读相关定义和原生fixture测试，不复制一套解析器或改成app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 135／361866 |
| 产品源码 | 4896 行 Python，40 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | pyproject声明markdown-it-py>=2,<5、Python>=3.10；上游tox实际测试要求markdown-it-py>=4.1，本轮使用4.2.0，传递mdurl及testing额外pytest/cov/regressions/timeout等均冻结。GFM/自动链接本来就要求>=4.1，不能把所有插件承诺为核心2.0可用；无统一lock |
| 外部系统 | 无数据库/服务/浏览器或JS数学渲染引擎，全部原生观察在无网容器；base URL与issue链接提案只改Token，不访问远程资源 |
| 安装耗时 | 18.10 秒；受缓存与网络影响 |
| 独立 venv 大小 | 32,050,003 字节，含 pip 和本轮测试工具 |
| 原生基线 | 511 通过、0 失败、0 错误、0 跳过 |
| 测试进程墙钟／峰值 RSS | 1.28 秒／37,332 KiB |

完整原生pytest tests目录511通过、0失败/错误/跳过，未改/重生成fixture。已读上游AGENTS与tox配置；本轮直接运行其完整pytest测试命令并预备testing依赖，没有执行tox/uv外包装、mypy、pre-commit或Sphinx构建。当前来源基线成立，但不声称通过所有维护者开发工具或多Python/旧markdown-it版本矩阵。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

真实临时UTF-8文档中含front matter、中文标题及脚注，通过同一个MarkdownIt.parse得到metadata Token/env，再用原renderer输出HTML并写文件读回；确认mdit_py_plugins来自/tmp/source，核心版本4.2.0。20项原版观察包括两种循环的正常对照；触发子进程先打印READY证明已完成导入，再限制地址空间160MiB/等待1秒，超时kill并wait回收，容器无OOM。

12项已复现修复：GFM www链接正文不前进、texmath越出引用父块不前进、dollarmath保留引用标记/吞后续列表、attrs span绕过allowed/闭合元素class合并丢值、tasklists label_after错误/空白不一致、GFM拒绝链接回退丢前缀、footnote docId属性未转义、texmath编号模板闭包串值及front matter点结束符错位。8项增强基于真实缺口：可定制metadata标记、容器参数属性、锚点回调/保留显式id、details提示、base URL、issue链接和line blocks。

已有脚注/内联脚注及docId前缀、定义列表、上下标、单行/块属性与allowed、容器/折叠class、Math多种分隔和renderer回调、front matter Token、字数env、MyST role/target/替换、GFM表格/删除线/任务/alerts。tasklists enabled=True已支持可点复选框，#59不能重复做一遍；anchors实体标题在当前核心text_join后正确，已实际排除错误怀疑。metadata可一次parse+renderer取得，不把#133文档说明或再次parse计增强；缺省数学HTML已经可由用户提供renderer，不声称新增一组delimiter就是独立能力。

## 二十步路线与接入边界

20项为12项复现修复、8项独立增强。两种循环按不同插件/触发机制各为一项；同一循环的五种delimiter只作该项矩阵。源包括#160/#156/#125/#147/#134/#129/#7/#96/#113/#106/#10及实际attrs/tasklists/footnote/texmath代码观察。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。后续须调用候选插件注册到真实MarkdownIt并校验Token结构、位置前进、env和渲染结果，回归完整511项与此前增强；循环样例始终由控制端有界执行。依赖核心和插件分别固定，不以核心开发分支修复替代本插件交付。512MiB/PID128和子进程160MiB限额均如实记录，不等于默认256MiB验收或正式verifier可用。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/mdit-py-plugins/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/executablebooks/mdit-py-plugins.git <checkout>
git -C <checkout> checkout --detach 519953da0a394a92534bc27580f4e7415462df44
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest pytest-cov pytest-regressions pytest-timeout 'markdown-it-py>=4.1.0,<5.0.0'
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mdit-py-plugins baseline -- \
  -m pytest tests -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mdit-py-plugins observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
