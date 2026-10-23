# 真实 GitHub 项目审查：mistletoe

研究日期：2026-10-21。适合真实可扩展Markdown AST与多格式渲染工程，按本仓特有的Token父子关系、全局解析规则、Markdown回写和LaTeX出口规划。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./mistletoe-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[miyuchina/mistletoe](https://github.com/miyuchina/mistletoe)，元数据归档状态为 false。
- 完整固定提交：[ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7](https://github.com/miyuchina/mistletoe/tree/ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7)，包版本 1.7.0.dev。
- 许可证：产品MIT；附带CommonMark 0.30规范示例另为CC BY-SA 4.0；Markdown语法文档样例采用原作者BSD风格许可，jQuery README样例为MIT。已保留项目LICENSE、John MacFarlane的CommonMark署名和CC-BY-SA-4.0.txt；本地commonmark.json与官方0.30/spec.json逐字节相同，652例。另核对并保存John Gruber的原Markdown许可页；jquery.md与官方jQuery3.2.1 README逐字节相同，保存该tag的JS Foundation MIT许可，不能把这些外来样本统一改标为本项目MIT。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

Document先建块Token，再解析span；Token.children设置parent，utils.traverse提供广度遍历。BaseRenderer按类名映射方法并增删模块全局_token_types，退出重置；HtmlRenderer控制原生HTML/转义；MarkdownRenderer注册BlankLine和引用定义以保留回写；LaTeXRenderer收集依赖包输出文档；AstRenderer导出调试JSON；contrib含TOC、MathJax、Pygments、Jira/XWiki和Scheme。CLI支持文件/多个输入和REPL。已读这些类、签名、字段与对应测试，未移植为通用app.py。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 91／535862 |
| 产品源码 | 4710 行 Python，25 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 基础产品无必需第三方依赖。按上游requirements/test-requirements安装parameterized、pytest和可选Pygments>=2.11.2,<=2.16，实际Pygments2.16.0等版本冻结；不把上游Python3.5兼容约束误升级到最新Pygments。没有统一lock |
| 外部系统 | 无数据库、云服务或网络；本轮不安装TeX引擎，不编译LaTeX，不访问浏览器或Jira API。ADF只核对官方结构及能力缺口，无外部写入 |
| 安装耗时 | 11.47 秒；受缓存与网络影响 |
| 独立 venv 大小 | 26,026,569 字节，含 pip 和本轮测试工具 |
| 原生基线 | 349测试项通过、3 subtests通过、1上游跳过；另652 CommonMark例通过 |
| 测试进程墙钟／峰值 RSS | 1.36 秒／53,440 KiB |

完整原生pytest test目录：349测试项通过、1上游已标记跳过、另3个subtest通过。pytest9的JUnit将3个subtest也序列化为成功testcase，因此XML/机器原始计数为352条通过记录、1跳过；两种口径明确不冒充352个独立测试项。跳过是上游已注明的表格管道语法边界，非本轮手工skip。额外原生命令python -m test.specification --ignore-known执行全部652个CommonMark0.30例，KNOWN=[]，全部通过，无额外排除。未跑旧test_ci.sh回退git历史、性能benchmark、多Python或文档发布；不改上游测试。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

真实CLI将临时UTF-8 Markdown文件的标题与粗体转换成HTML，再写临时文件读回；模块来自/tmp/source/mistletoe。20项观察中存在独立源码/CLI/AST/多renderer调用；stdin原生子进程只做0.1秒有界观察并回收，明确的EOF重复处理证据另由受控input序列（两次EOF后KeyboardInterrupt）得到，不把短进程仍运行本身当作已证明无限循环。

10项复现修复涉及Heading.content串值、BaseRenderer断行叶节点、空TOC、默认filter列表共享、嵌套renderer重置外层规则、AST子节点生成器消耗/父关系、Markdown回写语义丢失、深列表RecursionError、不兼容CLI renderer的KeyError和LaTeX文字转义。10项增强是选择性原HTML标签、URL协议策略、定义列表、引用脚注、ADF、无表头表格、智能标点、精确源码区间、目录跳转及管道stdin。危险URL只观察合成字符串输出，不给未核实上游issue冠以已获CVE或声称浏览器执行成功。

已支持块起始line_number、Token.parent、带深度/类过滤的traverse、表格和删除线、HTML全部禁用转义、AST/HTML/LaTeX/Markdown/Jira/XWiki等出口、引用链接定义回写、TOC文字列表、Pygments着色和Markdown折行。#144的块行号已存在，不重复计步；#210旧remove_token ValueError在该commit已做幂等保护，不照抄为当前BUG。Footnote类实际是链接引用定义，不等于[^n]引用脚注；补尾换行是renderer既有行为，不当作缺陷凑步。

## 二十步路线与接入边界

20步为10项实际修复与10项增强。将同一AST children契约的可迭代值/parent一致性合为一项，将Markdown实体还原后产生语法的问题合一项；没有按实体字符、表格列数、TOC级别或HTML标签拆成独立迭代。来源为固定代码、上游#212/#208/#210/#264/#279/#301/#269/#235/#47/#230/#60/#139/#144/#302及真实使用场景。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。后续原生验收要同时校验AST结构/parent、HTML输出和Markdown往返语义；累积保持652个既有CommonMark样例，并单独记录改进影响。暂不引入TeX/Jira在线服务；ADF离线输出可冻结官方schema子集。许可归属随源快照保留；512MiB/PID128不代表默认256MiB、线程并发已经可靠或现有verifier能接入。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/mistletoe/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/miyuchina/mistletoe.git <checkout>
git -C <checkout> checkout --detach ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest parameterized 'Pygments>=2.11.2,<=2.16'
```

额外原生规范命令：`.deploy/project-iteration-repairs/venv/bin/python .deploy/github-100-research/text-formats/research_tools.py run mistletoe commonmark-native -- -m test.specification --ignore-known`；对应日志与资源在 `commonmark-native-output/`、`commonmark-native-result.json`，652例全部通过。

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mistletoe baseline -- \
  -m pytest test -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run mistletoe observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
