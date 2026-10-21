# 模板与结构化文档候选研究

研究日期：2026-10-21。范围为本轮规划研究，不修改正式题库、候选源码或线上环境，不运行被测模型。本文中的物料文件名、任务 ID 和预算均为待规划冻结的建议，不表示这些验收资产已经实现。

## 结论与候选比较

首批推荐 **Jinja，4 个业务场景、12 个稳定任务，其中 2 个修改任务**。它增加模板编译、加载与缓存、渲染数据、同步与异步执行等业务面，与现有 python-frontmatter 的元数据读取及保真编辑区别明显。后两库仍可进入后续项目池，不用既有二十步路线自动生成二十个任务。

| 候选 | 固定版本与许可 | 原生与离线适配 | 与既有内容差异、优先级 |
| --- | --- | --- | --- |
| Jinja | [pallets/jinja@5ef70112a1ff19c05324ff889dd30405b1002044](https://github.com/pallets/jinja/tree/5ef70112a1ff19c05324ff889dd30405b1002044)，3.2.0.dev，BSD-3-Clause | `src/jinja2` 原生导入，Python >=3.10；核心仅 MarkupSafe>=3；历史 Python3.12.3 基线 911 通过，3.785 秒、峰值 77652 KiB、venv 87,208,816 字节 | 模板复用、环境配置、生成内容、异步物化，新增覆盖最多；**首批** |
| TOMLKit | [python-poetry/tomlkit@eddd27e43a62fe58707c311bfad2f52e72493f53](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53)，0.15.2，MIT | `tomlkit` 原生导入，无核心第三方依赖；历史 Python3.12.3 基线 1203 通过，2.481 秒、峰值 55020 KiB、venv 45,946,506 字节 | 配置树/片段代理比 frontmatter 更深入，但注释保真与最小变更需求重复；**后批**。完整基线还须固定 `tests/toml-test` 子模块 |
| xmltodict | [martinblech/xmltodict@6e29fba282e68631034dd2722a413b4e35276584](https://github.com/martinblech/xmltodict/tree/6e29fba282e68631034dd2722a413b4e35276584)，1.0.4，MIT | 单文件 `xmltodict.py`，核心仅标准库；历史隔离账号镜像原生 134 通过、1.131 秒、峰值 40044 KiB；256 MiB、无网、UID1000 已有证据 | 增加 XML 交换/流式消费，但二十步多为新接口与明确非目标的增强，不能直接标为二十个上游缺陷；**后批** |

以上完整测试计数均引用既有证据，本轮没有重复整套原生测试。1536 MiB 候选容器预算从历史原生进程量级看有较大空间，但历史 RSS 不是模型 CLI 加全部角色的总内存保证，也不是当前正式镜像的重新实测。

## 来源与实际核验

已读取三个项目的 `research/github-projects/<name>.md` 和 `<name>-roadmap-20.md`，以及下面的本地固定源码。三者 `git rev-parse HEAD` 与表中完整提交一致，`git status --porcelain` 均为空；官方 origin 分别为表中 GitHub 仓库。

| 项目 | 本地源码 | 历史测试证据 |
| --- | --- | --- |
| Jinja | `/tmp/github-research-jinja-tzuvabrq/source` | `.deploy/github-100-research/cli-config/jinja/baseline-result.json`、`baseline-tests.xml` |
| TOMLKit | `/tmp/github-research-tomlkit-4z5_8onf/source` | `.deploy/github-100-research/cli-config/tomlkit/baseline-result.json`、`baseline-tests.xml` |
| xmltodict | `.deploy/github-100-research/data-tools/xmltodict/source` | `.deploy/github-100-research/data-tools/xmltodict/baseline-result.json`、`baseline-output/baseline-tests.xml` |

本轮官方 GitHub 网页经 web 工具访问被限制；没有据搜索摘要补写事实。改用官方 raw.githubusercontent.com 对三个固定提交的许可证和 `pyproject.toml` 做只读 HTTP 获取，六个请求均 200，响应与本地文件逐字节一致：

- Jinja：[许可证](https://raw.githubusercontent.com/pallets/jinja/5ef70112a1ff19c05324ff889dd30405b1002044/LICENSE.txt)，SHA256 `3b49dcee4105eb37bac10faf1be260408fe85d252b8e9df2e0979fc1e094437b`；[项目定义](https://raw.githubusercontent.com/pallets/jinja/5ef70112a1ff19c05324ff889dd30405b1002044/pyproject.toml)，SHA256 `b62064bf51527e22712e9b307c6948ce7261ef9cca65d7d7e5c0e0996630dcb3`。保留 Pallets 版权、三项条件与免责声明。
- TOMLKit：[许可证](https://raw.githubusercontent.com/python-poetry/tomlkit/eddd27e43a62fe58707c311bfad2f52e72493f53/LICENSE)，SHA256 `f2f9b460ba719da6626add264d3782f275a4ff7aab677beda08b330911e23adb`；[项目定义](https://raw.githubusercontent.com/python-poetry/tomlkit/eddd27e43a62fe58707c311bfad2f52e72493f53/pyproject.toml)，SHA256 `6c661a9f6c585bcd14bef624b89ebf5d0790d637feac5f81e3c582b22ab9458b`。保留 Sébastien Eustace 版权和 MIT 许可；若纳入外部测试语料，另保留其许可。当前检出的 `git submodule status` 为 `-08ed8697864548b3cdb4b8decbf496bef47e1c82 tests/toml-test`，即语料当前未展开；历史 1203 计数是在展开固定 gitlink 后完成，二者不可混同。
- xmltodict：[许可证](https://raw.githubusercontent.com/martinblech/xmltodict/6e29fba282e68631034dd2722a413b4e35276584/LICENSE)，SHA256 `d66d5eb8f83a0ba21d3dd04318b8817588e8764daabea852d1035e3f07ffda55`；[项目定义](https://raw.githubusercontent.com/martinblech/xmltodict/6e29fba282e68631034dd2722a413b4e35276584/pyproject.toml)，SHA256 `c141a53cd799c9863b7650f7853ad20e931f387f6700c19b0a63e00ce32e2ec8`。保留 Martin Blech、贡献者版权与 MIT 许可。

TOMLKit 已核 `api.parse`（api.py:103）实际调用 `Parser(string).parse()`，`dumps`（:57）可直接输出原生文档；`TOMLFile.read/write`（toml_file.py:29、:48）记录换行后直接写文件。xmltodict 已核 `parse`（xmltodict.py:208）文件/字符串/generator 三条实际入口，`_DictSAXHandler`（:15），`unparse`（:567）；README/AGENTS 明确不保证完整混合内容顺序。没有把原有能力或既定限制算成新 BUG。

## Jinja 的共同冻结与验收边界

建议中文项目展示为“Jinja 报表模板工作场景”。所有模型首问、后续披露和评审要求用英文；项目介绍、任务 `goal`、场景及浏览路线用中文。以下中文用户问题用于产品展示与需求核对，英文首问是对应待冻结输入。

- **共同源码证据**：所有锚点相对于固定 `5ef70112a1ff19c05324ff889dd30405b1002044` 的源码；路径/方法均已读实际定义。不得用系统安装的另一版 Jinja 代替候选代码。
- **共同依赖**：冻结 Python3.12 环境，直接从候选 `src` 导入 Jinja2，第三方 wheel 预备到只读离线环境。历史锁含 MarkupSafe3.0.4、Babel2.18.0、pytest9.1.1、pytest-timeout2.4.0、trio0.34.0 及其传递依赖；正式接入时按完整冻结文件与 wheel SHA256 固定，而非安装运行时最新版。Babel 用于完整 i18n 回归；首批业务无翻译服务。
- **共同物料**：合成报表、模板与调用方代码，不含真实客户、账号或配置。物料初始公开项、按需披露项及私有独立 oracle 分开。物料和源码快照在正式接入阶段冻结摘要，本文没有伪造它们已生成的 SHA。
- **问答任务**：`allowed_paths=[]`，允许答案中提供最小示例。原生检查可验证示例、冻结事实和无源码变更；自然语言解释必须由语义 rubric 判断，不能只靠关键词或原生测试自动判为完整回答。模拟只能验证流程，不证明真实模型语义评分。
- **修改任务**：仅 JI-M01、JI-M02 接受代码能力；两者共同允许 `src/jinja2/filters.py`、`tests/test_filters.py`、`tests/test_async_filters.py`。私有验收、原始回归、依赖、执行器及输出标记不在允许路径内。接续同一场景时累计保留已通过修复，第二项必须复验第一项。
- **独立原生验收**：控制端检查 `jinja2.__file__` 和有关函数源码路径均在候选目录；可信测试从控制端冻结，候选测试通过不能单独放行。用标准库 `urllib.parse`、普通 Python 值及真实文件字节作独立输出对照，适用原生 911 基线仍从可信原版测试快照执行。
- **必要最小适配**：主代理已核现有 `project_native_regression.py` 的 `SUITES` 仅覆盖原3仓，`_overlay` 默认 `candidate/package`、`_run` 默认将项目根放入 `PYTHONPATH`。Jinja 实际为 `src/jinja2`，需在受控 suite 中明确候选实现目录和导入根，保持原3仓默认行为；不能把 `src/jinja2` 当 Python 模块名，也不能误导入已安装 site-packages。历史911只是该固定源码旧环境基线，本轮尚未生成当前账号镜像下的完整节点 contract，实施时必须重新冻结节点集合及预期结果，不能把旧计数当新 wrapper contract。
- **资源建议**：原生微场景用数项/至多数百项合成数据、临时目录、无网；默认检查超时可先设 15 秒，完整回归先设 60 秒，均待正式镜像实测再定。问答累计预算建议 300 秒、诊断/方案 600 秒、修改 1800 秒；是可调规划值，不是已实测模型耗时。保持现有 1536 MiB 候选预算，不引入数据库/浏览器/外部服务。

## 场景一：接入中文周报与通知模板

### JI-U01｜understand｜理解项目与渲染流程

- **中文用户问题 / goal**：这个项目能帮我们做什么？周报模板从加载到输出经过哪些组件，和 Markdown 元数据编辑有什么区别？
- **英文首问**：`Explain what this pinned Jinja project does and trace a weekly-report template from loader to rendered text. Identify the roles of Environment, Template, the context, inheritance, and filters, and explain whether this is a lossless document editor. Do not change files.`
- **源码证据**：[Environment](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/environment.py#L145)、`_load_template`（:956）、`Template.render`（:1272）、`Template.stream/generate`（:1317/:1323）；`DictLoader`（loaders.py:432）。
- **冻结材料/披露**：首轮 `materials/JI-S01/brief.md`、`base.html`、`weekly.html`、三项合成指标及调用片段；完整材料直接可用，不应无故追问。
- **正常 oracle**：固定模板继承并渲染出带中文标题和三项指标的字面预期；解释与实际加载—编译—上下文—字符串输出一致。
- **反例 oracle**：更改一项指标只影响其输出；不能称 Jinja 为保留原始 frontmatter/Markdown 字节的编辑器，也不能称本地运行必需 Flask。完整快照摘要不变。
- **允许路径/依赖/资源**：`[]`；共同依赖；小型同步渲染，15 秒检查。未验证原生程序能独立评判整段解释，需语义 rubric。

### JI-C01｜consult｜选择 HTML 与纯文本的转义配置

- **中文用户问题 / goal**：同一批数据要生成网页周报和纯文本通知，怎样复用环境又得到正确的尖括号显示？
- **英文首问**：`We render both report.html and report.txt from the supplied trusted templates. Propose an existing Jinja configuration so the title <Review> is escaped in HTML and remains literal in plain text. Include one minimal runnable Python example. Do not change the library or templates.`
- **源码证据**：`Environment.__init__`（environment.py:311–316，`autoescape=False` 的真实默认）；[select_autoescape](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/utils.py#L581)，按模板扩展名/字符串来源作选择。
- **冻结材料/披露**：两份相同 `{{ title }}` 模板及数据 `<评审>`；不隐藏题目必要信息。
- **正常 oracle**：抽取回答内唯一 Python 示例，原生运行实际候选；HTML 字面 `&lt;评审&gt;`、TXT 字面 `<评审>`，再用 `html.unescape`核内容。
- **反例 oracle**：大写 `.HTML`、字符串模板默认策略；全局手工 HTML 转义会让纯文本错误，统一关闭转义使 HTML 输出错误。无需修改源码是正确结论。
- **允许路径/依赖/资源**：`[]`；共同依赖；15 秒。示例提取应复用已验证的单代码块规则，正式实现前不假定已有 Jinja 专用提取器。

### JI-P01｜plan｜规划业务模板覆盖与默认回退

- **中文用户问题 / goal**：各业务线只改少数模板，其余复用默认周报，如何组织加载器和发布方式？
- **英文首问**：`Design a small template-loading setup where a business unit can override selected templates and fall back to the shared defaults. Use existing Jinja APIs, define precedence and missing-template behavior, and explain how template updates become visible. Provide a plan only; do not implement it.`
- **源码证据**：[ChoiceLoader](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/loaders.py#L560)，`load`（:588）只捕获 `TemplateNotFound` 后回退；`Environment._load_template`（environment.py:956）。
- **冻结材料/披露**：`requirements.md` 明确模板均可信、覆盖来源顺序和共享 base；各来源只含合成模板，不需网络挂载。
- **正常 oracle**：可信模型将两层 DictLoader/ChoiceLoader 原生执行，覆盖项为 `CUSTOM`、默认独有项为 `BASE`；方案须对应这种优先级并说明重新获取模板和 reload 条件。
- **反例 oracle**：覆盖模板存在但语法错误，必须报原错误，不应当成不存在而回退；全部不存在报 `TemplateNotFound`。不能发明 `Environment.register_theme` 等 API。
- **允许路径/依赖/资源**：`[]`；依赖 JI-U01 的业务背景但不依赖其答案文本或代码检查点；15 秒小测试。计划可独立验收，不把后续实现另塞进本任务。

## 场景二：定位周报异常并判断是否需要改库

### JI-D01｜diagnose｜材料不足时先请求必要证据

- **中文用户问题 / goal**：周报渲染报 UndefinedError，是不是库有 BUG？
- **英文首问**：`Our weekly report raises UndefinedError. Is Jinja broken? I have not provided the template, rendering call, input data, or traceback yet. Diagnose only as far as the available evidence supports, and request the minimum missing material. Do not change files.`
- **源码证据**：`Undefined.__getattr__`（runtime.py:862）、`Undefined.__str__`（:892）、`StrictUndefined`（:1039）、`Environment.getitem/getattr`（environment.py:467/:484）。
- **冻结材料/披露**：首轮仅上述症状；合理请求后一次披露 `{{ account.name }}`、`render()` 无 account、完整栈和环境构造代码。另可配置“材料不可提供”的 entry；同一稳定任务，不把多轮或分支算成额外任务。
- **正常 oracle**：披露前接受有条件假设/索取模板与调用数据；披露后原生复现 `'account' is undefined`，补 `account={'name':'研发'}` 输出“研发”，据此定位调用数据缺失。
- **反例 oracle**：只给缺少叶子字段、给完整 account、或切 StrictUndefined 的可信对照，不允许泛称所有 undefined 都静默空串。不可提供材料分支应结束为 `insufficient_information`，不能自称已复现/确诊；可提供分支不得在披露后无限追问。
- **允许路径/依赖/资源**：`[]`；共同依赖；15 秒事实复现、600 秒累计预算建议；缺料分支不执行不存在的 reproducer。

### JI-D02｜diagnose｜更新模板后输出仍旧的原因

- **中文用户问题 / goal**：已经替换周报模板，为什么重新 get_template 后还是旧内容？
- **英文首问**：`The supplied service keeps an Environment with auto_reload=False. After its DictLoader mapping changes from v1 to v2, a fresh get_template call still renders v1. Explain the cause and give a minimal existing-API remedy, including what happens to an already-held Template. Do not change the library.`
- **源码证据**：`Environment.__init__`（environment.py:315–316）、`_load_template`（:956–975），`DictLoader.get_source`（loaders.py:444）返回比较原始内容的 uptodate 回调。
- **冻结材料/披露**：完整 `reproducer.py` 和 `v1/v2` 两字面模板；无缺料，禁止把缓存错认为网络或部署权限问题。
- **正常 oracle**：原版 `auto_reload=False` 先后为 `[v1,v1]`；新环境 `True` 且再次 get_template 为 `[v1,v2]`，或明确清空该环境缓存后重新加载。
- **反例 oracle**：已持有旧 Template 不会因为开关自动变成新对象；直接渲染旧对象仍可输出 v1；不要承诺 `auto_reload` 每次 `Template.render` 都访问来源。正确结果 `no_change_needed`。
- **允许路径/依赖/资源**：`[]`；共同依赖；15 秒。缓存和加载器的真实定义已核，不发明新的刷新 API。

### JI-D03｜diagnose｜末尾换行消失属于配置语义

- **中文用户问题 / goal**：纯文本周报导出少了末尾换行，是不是 stream 吞了字节？
- **英文首问**：`The supplied template is the exact text "x\n". Both render() and stream() omit its trailing newline under the default environment. Locate the behavior and recommend the smallest existing configuration change. Distinguish source-template newlines from newlines inside variable values. Do not patch Jinja.`
- **源码证据**：`Environment` 参数说明（environment.py:199，`keep_trailing_newline`）、[Lexer.tokeniter](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/lexer.py#L685) 的末空行处理，`Template.stream`（environment.py:1317）。
- **冻结材料/披露**：准确字节模板、两个调用和输出 repr，避免编辑器是否加换行的歧义。
- **正常 oracle**：默认真实输出 `x`，`keep_trailing_newline=True` 为 `x\n`，两条输出入口一致。
- **反例 oracle**：变量值自带换行不应用字符串无条件 `.rstrip()` 替代；无末换行的模板仍 `x`。这是已声明语义，无需修改库。
- **允许路径/依赖/资源**：`[]`；共同依赖；15 秒；多平台换行矩阵不在本任务承诺范围。

## 场景三：修复模板数据转换中的两个独立问题

### JI-D04｜diagnose｜查询字符串中的值为何变成键字符

- **中文用户问题 / goal**：报告下载链接从普通 dict 换成 UserDict 后，为什么 Aa 的值被渲染成 a？
- **英文首问**：`Using the supplied pinned checkout, explain why urlencode(UserDict({'Aa': 'A+1'})) produces A=a while the equivalent dict produces Aa=A%2B1. Identify the exact dispatch error, show a safe caller workaround, and delimit the affected inputs. Diagnose only; do not edit files.`
- **源码证据**：[do_urlencode](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/filters.py#L147)，标注 Mapping，但 :168 分支仅认 `dict`；其他 Iterable 直接按 pair 解包。
- **冻结材料/披露**：`UserDict({'Aa':'A+1'})`、相同 dict、单字符键及调用方代码，实际结果都可由候选复现；不靠 issue 标题判断。
- **正常 oracle**：上述输出分别 `A=a` 和 `Aa=A%2B1`；caller 使用 `.items()` 或 plain dict 获正确 query；`urllib.parse.parse_qsl` 解析后为 `[('Aa','A+1')]`。
- **反例 oracle**：单字符 UserDict 键产生 ValueError；pair 列表的重复键必须仍保留；字符串路径 `a/b c` 是 `a/b%20c`，不能一律 `.items()` 或把路径 `/` 改掉。
- **允许路径/依赖/资源**：`[]`；共同依赖；15 秒；可在本场景直接停于诊断，不强制进入修改。

### JI-M01｜modify｜支持标准 Mapping 的 urlencode

- **中文用户问题 / goal**：修复 UserDict 查询编码，保持现有字符串和键值对序列行为。
- **英文首问**：`Fix the demonstrated urlencode dispatch bug so standard Mapping implementations are encoded as their items. Preserve dict behavior, duplicate keys in pair iterables, and the existing string-path quoting rules. Limit changes to the allowed paths and include regression coverage.`
- **源码证据**：同 JI-D04 的 `do_urlencode`；模块已有 `from collections import abc`，可沿用真实导入，不需新增依赖或通用重构。这是固定原版 Mapping 类型契约与行为不一致的修复，不是承诺上游已接受的新功能。
- **冻结材料/披露**：独立 repro 与兼容要求；前置 JI-D04 只是可选业务路线，直接 repair entry 也必须给足相同物料。
- **正常 oracle**：可信测试使用 UserDict、自定义只读 `collections.abc.Mapping`、Unicode/单字符/两字符/空键；实际 query 经标准库 parse_qsl 后与原始 item 序列严格相同，包含 `+ & /`、空值和插入顺序。
- **反例 oracle**：pair iterable 重复键未丢，dict 与原始预期一致，字符串 `/` 原行为不变；非法 pair 原本异常不能被吞并返回空串。可信原版 filters 测试与完整适用基线仍过。
- **允许路径/依赖/资源**：`src/jinja2/filters.py`、`tests/test_filters.py`、`tests/test_async_filters.py`；无新依赖；小 oracle15秒、回归60秒规划值；1800秒累计预算建议。

### JI-M02｜modify｜区分缺省 default 与显式 None

- **中文用户问题 / goal**：让 map(attribute=..., default=none) 对缺字段真正输出 None，同时保留已有值和未给 default 的行为。
- **英文首问**：`Fix map(attribute='field', default=none) so a missing field produces the explicit None default. Omitting default must retain the existing Undefined behavior, and existing None, False, 0, and empty-string field values must remain unchanged. Cover synchronous and asynchronous templates and preserve the previously accepted urlencode behavior.`
- **源码证据**：`make_attrgetter`（filters.py:58，:75 以 `default is not None` 判断）；`prepare_map`（:1718，:1723 `kwargs.pop('default', None)`）；`sync_do_map`（:1451）、异步 `do_map`（:1521）。当前两处把“未提供”和显式 None 混同，非凭空假设有新 API。
- **冻结材料/披露**：`rows=[{}, {'field':None}, {'field':False}, {'field':0}, {'field':''}]`、显式/省略 default 两调用；同步及异步模板。要求不擅改所有缺值的全局表现。
- **正常 oracle**：可信普通 Python 字段查找构造字面/类型对照，显式 None 首项 `is None`，后四项类型和值保持；显式 0/False/空串也分别回填，异步结果一致。
- **反例 oracle**：省略 default 首项须仍 `Undefined`，不能只按渲染空串比较；真实 `None` 字段不得替成其他 default；嵌套缺父字段、StrictUndefined 与共享 getter 其他调用方回归，不把异常吞成空串；重跑 JI-M01 oracle。
- **允许路径/依赖/资源**：同 JI-M01；默认哨兵是实现可能方案，验收只约束行为，不冻结实现形状；无新依赖；小 oracle15秒、回归60秒规划值；1800秒累计预算建议。共同 getter 影响范围比 M01 大，必须查看全部调用点并做累计回归。

## 场景四：评估批量生成、依赖分析和导出边界

### JI-C02｜consult｜异步数据排序是否需要改引擎

- **中文用户问题 / goal**：异步周报里 map 后 sort 失败，现有接口能否解决？排序还能不能全程流式？
- **英文首问**：`In enable_async=True, the supplied rows|map(attribute='x')|sort expression raises TypeError. Explain the sync/async boundary and propose an existing-filter workaround for our bounded 200-row report. State whether sorting can remain fully streaming. Provide a minimal runnable async example; do not modify Jinja.`
- **源码证据**：`do_sort`（filters.py:386，使用 Python sorted）、`do_map`（:1521，async generator）、`do_list`（:1365，async_variant）、`Template.render_async`（environment.py:1294）。
- **冻结材料/披露**：完整 async 调用、两个 `{x:...}` 对象，业务明确最多200行；不制造无限输入场景。
- **正常 oracle**：原版链实际抛 `'async_generator' object is not iterable`；调用方先 `|list` 再 `|sort` 得 `['a','d']`，同步同数据作对照。
- **反例 oracle**：逆序/重复键与空输入正常，不能承诺全排序是常量内存或仍可无限流；不建议在活动事件循环调用 `asyncio.run`。无需修改库的可行方案为正确结果，异步 sort 增强留后批。
- **允许路径/依赖/资源**：`[]`；共同依赖、标准库 asyncio；15秒，200行有界物化；大型性能对比不在本任务范围。

### JI-P02｜plan｜静态依赖与实际动态依赖的边界

- **中文用户问题 / goal**：想按模板依赖做增量重建，meta 能不能告诉我们动态 include 最后选中了谁？
- **英文首问**：`Plan dependency tracking for an incremental report builder. The supplied template extends 'base.html' and includes the runtime variable section. Explain what find_referenced_templates can prove, what remains unknown, and how an application could obtain actual dependencies for a render without claiming a new built-in Jinja API. Give a plan only.`
- **源码证据**：[meta.find_referenced_templates](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/meta.py#L62) 对动态引用返回 None；`compiler.visit_Include`（compiler.py:1036）选择加载入口；`Environment._load_template`（environment.py:956）包括缓存命中。
- **冻结材料/披露**：完整模板、两组 `section` 变量及重建要求；没有要求新增 Jinja API。
- **正常 oracle**：静态结果明确 `['base.html', None]`，不同 section 原生渲染实际不同页面；方案区分“所有可能依赖”与“本次实际依赖”，给出调用方记录/显式依赖登记的边界。
- **反例 oracle**：不能把 None 当成“没有依赖”，不能仅靠 loader 的 `get_source` 钩子宣称覆盖缓存命中的每次 render；方案需说明缓存、fallback、重复依赖与并发记录隔离。
- **允许路径/依赖/资源**：`[]`；共同依赖；15秒事实检查；真实运行期 collector 是后续可选增强，不能把计划当已实现检查点。

### JI-C03｜consult｜Path 导出报错时采用兼容调用

- **中文用户问题 / goal**：stream.dump(Path(...)) 报错，当前版本如何兼容 pathlib，并正确管理调用方文件流？
- **英文首问**：`Template.stream().dump(Path('report.html')) raises AttributeError in the supplied checkout. Explain why and show a minimal caller-side solution using existing APIs. Cover UTF-8 Chinese text and caller-owned text/binary streams, including ownership. Do not change the library.`
- **源码证据**：[TemplateStream.dump](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/src/jinja2/environment.py#L1585)，只有 str 分支打开文件，其他对象按流写；finally 仅关闭自己打开的文件。
- **冻结材料/披露**：Path 调用、合成中文模板和导出要求；本轮如实定位不支持 PathLike，不宣称已有 API 承诺支持任意路径对象。
- **正常 oracle**：`dump(str(path))` 写出的 UTF-8 字节等于 `'中文'.encode('utf-8')`；`StringIO` 不编码、`BytesIO` 明确 encoding 后内容正确；调用方流保持打开。
- **反例 oracle**：错误流类型/写入错误须传播，不得无条件 close 调用方流或吞错误；原版 Path 失败作为固定事实。`PathLike` 库增强列后备，不作为第三个修改任务加入本批。
- **允许路径/依赖/资源**：`[]`；共同依赖、标准库 pathlib/io；只写合成临时目录并销毁，15秒；Windows 路径行为未实测，不声称已覆盖。

## 本轮新增微复现记录

在既有 Jinja 专用 venv，以 `python -B` 从干净固定 checkout 导入候选运行少量直接 API 场景，未运行完整 pytest。实际 `jinja2.__file__` 为 `/tmp/github-research-jinja-tzuvabrq/source/src/jinja2/__init__.py`，Python3.12.3。工具返回 exit0、子进程约0.068秒。文件导出仅使用自动清理的临时目录。

| 调用/观察 | 本轮真实结果 |
| --- | --- |
| `do_urlencode({'Aa':'A+1'})` | `Aa=A%2B1` |
| `do_urlencode(UserDict({'Aa':'A+1'}))` | `A=a` |
| `do_urlencode(UserDict({'q':'A+1'}))` | ValueError，expected2/got1 |
| pair 重复键、字符串路径对照 | `q=a&q=b`；`a/b%20c` |
| map 省略 default 与显式 None 的首项 | 两者均为 `Undefined`；其余 None/False/0/空串类型和值保持 |
| map 显式0的缺字段首项 | `int`，0；已有 None 仍 None |
| 缺根 account、`{{ account.name }}` | 默认 Undefined 和 StrictUndefined 均抛 `'account' is undefined` |
| DictLoader 更新映射后重新 get_template | auto_reload=True 为 `[v1,v2]`；False 为 `[v1,v1]` |
| 同标题 `<评审>`，HTML/TXT 扩展名自动选择 | `&lt;评审&gt;`；`<评审>` |
| 源模板 `x\n`，keep_trailing_newline False/True | `x`；`x\n` |
| ChoiceLoader 覆盖项/仅默认项 | `CUSTOM`；`BASE` |
| 静态 meta 分析常量 extends+动态 include | `['base.html', None]` |
| async map 后直接 sort | TypeError：`'async_generator' object is not iterable` |
| Path dump / str(path) dump / StringIO dump | Path 为 `AttributeError: 'PosixPath' object has no attribute 'write'`；str路径正确UTF-8字节；StringIO内容“中文”且未关闭 |

另用第二个只读微进程核验了方案正对照（exit0、约0.015秒）：async `map|list|sort|list` 得 `['a', 'd']`；reload 后旧/新 Template 分别为 `v1/v2`；BytesIO+UTF8 得“中文”的准确字节且仍打开；变量值 `x\n` 保留换行。没有以文档推测代替这些可运行正例。

这些是固定原版现状取证，不是两项修复已通过，也不是12个正式任务已运行。尚需在实施阶段生成冻结物料、私有 oracle、语义 rubrics、原版失败/参考修复通过/破坏兼容反例三类校准、正式离线 wheel 包与运行证据。当前正式镜像 Python 补丁版本、1536 MiB 下整包模拟与未知回答语义能力均不从本轮微复现推断完成。

## 交付边界与后续收敛

- 本推荐12项分布为 understand1、consult3、diagnose4、plan2、modify2；场景与任务数服务业务覆盖，不为凑固定20步拆测试、文档、材料补充或失败重试。
- 无需修改至少覆盖转义配置、缓存、尾换行、异步有界物化和导出兼容；信息不足由 JI-D01 的不可提供材料 entry 正式表达。它们不能被评为“模型没写代码所以失败”。
- 两项修改目标已在固定原版真实复现；M01对应声明的Mapping协议分派不一致，M02对应显式None缺省语义。没有修改上游或声称上游承诺采纳。
- 母任务仅保留此研究文档；首批子任务可据此选择12项或进一步缩减，不应把本研究阶段新增为正式catalog版本。
