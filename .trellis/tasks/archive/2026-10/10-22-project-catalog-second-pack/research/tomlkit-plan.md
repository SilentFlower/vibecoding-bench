# Research: TOMLKit 第二批真实场景规划

- Query: 在固定真实版本上确定 TOMLKit 的来源、外部测试语料、依赖和可独立验收场景；保留无需改库及材料不足的正确结果，选择约两项窄修改。
- Scope: mixed；仅规划研究、只读源码、少量原生内存内复现与官方来源核对；未制作正式内容包或参考实现。
- Date: 2026-10-22。
- Active task: `.trellis/tasks/10-22-project-catalog-second-pack`。

## Findings

### 1. 建议范围与去重结果

建议 **5 个场景、12 个独立任务，10 个非修改、2 个修改**；类型为 understand 1、consult 3、diagnose 4、plan 2、modify 2。每个修改包含其测试与文档要求，不另拆任务；披露、不可提供材料、直接修改入口和重试也不另计。

| 场景 | 中文展示与业务边界 | 稳定任务 ID | 数量 |
| --- | --- | --- | --- |
| TK-S01 | 配置编辑接入与局部保真：读懂项目、保留既有样式、区分字面键与路径 | TK-U01、TK-C01、TK-C02 | 3 |
| TK-S02 | 解析失败与方言兼容：先索取缺失证据、识别 TOML 版本差异、规划消费者兼容 | TK-D01、TK-D02、TK-P01 | 3 |
| TK-S03 | 数组扩容一致性：诊断与修复原位重复后的逻辑／文本分歧 | TK-D03、TK-M01 | 2 |
| TK-S04 | inline 点分配置删除：诊断与修复最后叶子删除后的空表与分隔符 | TK-D04、TK-M02 | 2 |
| TK-S05 | 编码扩展与写盘边界：已有自定义编码器、调用方写盘方案 | TK-C03、TK-P02 | 2 |

相较 python-frontmatter，本仓重点是完整 TOML 文档树、类型／Trivia、字面与点分键、1.0／1.1 方言、inline 子树和数组原位操作。没有将旧二十步路线逐条转成新任务；代理表合并、递归排序、源位置、新路径 API、事务补丁等不进入本批。

### 2. 来源、实际文件与外部语料

**主仓**：[python-poetry/tomlkit@eddd27e43a62fe58707c311bfad2f52e72493f53](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53)，`pyproject.toml:3` 为 0.15.2；`requires-python >=3.9`，MIT，保留 2018 Sébastien Eustace 归属及完整 LICENSE。主 LICENSE SHA256 为 `f2f9b460ba719da6626add264d3782f275a4ff7aab677beda08b330911e23adb`，pyproject SHA256 为 `6c661a9f6c585bcd14bef624b89ebf5d0790d637feac5f81e3c582b22ab9458b`。

本次未执行任何 Git 命令。读取本地 `.git/HEAD` 为上述完整 SHA，并通过 [官方递归 tree API](https://api.github.com/repos/python-poetry/tomlkit/git/trees/eddd27e43a62fe58707c311bfad2f52e72493f53?recursive=1) 对照全部本地文件的 Git blob SHA1（`blob <len>\0<bytes>`）：**82 个普通 blob 全匹配，缺失／不同均为 0，API truncated=false**。tree 另有一个 mode=160000、type=commit 的 `tests/toml-test` gitlink；历史“83 个跟踪条目”包含这个 gitlink，不等于 83 个普通源码文件。

固定检出路径记为 **S = `/tmp/github-research-tomlkit-4z5_8onf/source`**。下文源码行号均相对 S，不表示这些文件已进入正式 `seed/library/`。

**外部语料**：主仓 `.gitmodules:1` 指向 `https://github.com/BurntSushi/toml-test.git`，gitlink 精确 SHA 为 **`08ed8697864548b3cdb4b8decbf496bef47e1c82`**。本次 `S/tests/toml-test/` 为空目录，`.git/modules/tests/toml-test` 也不存在；不能在此原样直接收集完整测试。

本次实际只读下载 [该 SHA 的官方 codeload 归档](https://codeload.github.com/BurntSushi/toml-test/tar.gz/08ed8697864548b3cdb4b8decbf496bef47e1c82)，在内存读取，不写入／展开到现有检出：

| 事实 | 本次真实结果 |
| --- | --- |
| HTTP | 200，可取得 |
| gzip 字节／SHA256 | 98,350／`2293a0b80a673c6dcc5c74eceb930d99f8396d2adf42afd61f26dd4fae6e144d` |
| 普通文件数／总展开字节 | 1,042／327,503 |
| 归档中许可 | 根 `LICENSE`；MIT，2018 TOML authors；SHA256 `01ef58ee6449fa01a284c10808e27800d66bfea271bc29281125ff8e5642b86f` |
| `tests/files-toml-1.1.0` | 894 行，含 .toml 和对应 .json，不能按 894 计测试；实际 .toml 680 个 |
| 清单 SHA256 | `296ae98086c0dcf52a0c656e3246a1ef3a3880832758e2d4a04b00e402e505ed` |
| 894 个清单引用文件 | 归档中全部存在，缺失 0 |
| 子模块逐 blob 来源核对 | 官方固定 tree API 的1,042个 blob与归档逐Git blob SHA1全部相同；缺失／多余／不同各0，truncated=false，无链接／特殊成员 |

正式入库时应将固定语料展开到 `library/tests/toml-test/` 并保留独立 LICENSE，同时在来源报告保留主仓 gitlink 和子模块逐文件来源清单。不能改为下载 master、删掉 `test_toml_tests.py`、只放文件列表而遗漏 JSON／编码反例，或把缺料 collection error 叫作产品 BUG。主仓与展开语料合计约 1,124 个来源普通文件，仍在当前每项目 10,000 文件限制内；最终数量须依实际纳入的来源文件清单重算。

### 3. 已读取的相关定义与代码模式

| 文件／行号 | 已核定义和与本批的关系 |
| --- | --- |
| `README.md:16`、`:29` | 明确 1.1.0-compliant；也声明一种 AoT 后置子表的布局归一化限制，不能承诺任意文档绝对逐字保真 |
| `tomlkit/api.py:48`、`:57`、`:81`、`:88`、`:103` | loads/parse → Parser；dumps 对原生 Table／Container 直接 as_string；load/dump 为文件流入口 |
| `tomlkit/toml_document.py:4`、`container.py:105`、`:131` | TOMLDocument 是 Container；逻辑值 unwrap 与保留片段的 `_body` 不是同一表示 |
| `tomlkit/api.py:158`、`items.py:2247`、`:2278`、`:2300` | `string(raw, literal=False, multiline=False, escape=True)`、String.type／from_raw；普通 str 赋值不承诺继承旧引号；显式 string 可实现安全既有调用 |
| `tomlkit/api.py:276`、`container.py:891` | 单字符串 key 是一个字面键；Iterable[str] 构造 DottedKey。索引不自动解释传入字符串中的点 |
| `tomlkit/container.py:936`、`:946`、`:1021` 附近 | 既有替换通道复制 indent/comment_ws/comment/trail；不得用 unwrap 后整体重建替代保真编辑 |
| `tomlkit/items.py:1421`、`:1509`、`:1622`、`:1637`、`:1706` | Array 同时维护 list、`_value`、`_index_map`，as_string 读片段，clear/insert/delete 同步两套表示 |
| `tomlkit/_types.py:44` | `_CustomList(MutableSequence, list)` 只定义 add/iadd，没有 imul；本批 Array 原位重复继承 list.__imul__，绕过 Array 片段维护 |
| `tomlkit/items.py:1781`、`:1834`、`:2059`、`:2104`、`:2213` | AbstractTable.remove → Container.remove；InlineTable.as_string／_render_dotted 展平 dotted 子表；最后叶子删除后空子表当前渲染列表为空，但该结构仍是键节点 |
| `tomlkit/container.py:572` | remove 用 `(None, Null())` 留删除占位，并非删除全部原始片段；普通删除回归有严格空白断言 |
| `tomlkit/parser.py:93`、`:164`、`:700`、`:815`；`exceptions.py:10` | 真实 Parser、parse_error、inline 解析和 escape；ParseError 有 line/col，缺文档时不能从异常类别唯一判因 |
| `tomlkit/api.py:355`、`:376`、`items.py:222` | register_encoder/unregister_encoder 与进程全局 CUSTOM_ENCODERS；编码器须返回 Item，不支持值应抛 ConvertError，后续编码器才有机会 |
| `tomlkit/toml_file.py:18`、`:29`、`:48` | TOMLFile 支持 str／PathLike；read 记录 LF／CRLF／mixed，write 序列化后直接文本 w 打开。没有 atomic、expected_digest 或锁参数 |
| `tests/test_toml_tests.py:15`、`:53`、`:121` | collection 时读取固定外部列表；有效输入与 tagged JSON 比较并核原文往返，非法输入／非法 UTF8 分别验异常 |
| `tests/test_items.py:1204`、`:1217`、`:1239`、`:1251` | 普通 inline 删除精确字节回归；已有 dotted 子表新增键正常行为。修改不能靠全表统一格式化使这些测试失效 |
| `tests/test_toml_file.py:36` 起 | 已有 LF／CRLF／mixed 和默认换行测试，不能把这些已有能力另立成待修缺陷 |
| `orchestrator/project_native_regression.py:51`、`:142`、`:156`、`:347` | suite 模块／物理目录／导入根契约及 baseline 测试恢复；TOMLKit 根包布局可用默认路径，原则上无需新布局适配 |

### 4. 共同材料、语言与依赖约定

- 页面 `title/category/description/goal` 中文；下列 English prompt、正式材料说明、分支 `when` 和 rubric 均英文；源码、原始错误和 `# 配置` 等业务字面保留。
- 下面物料名和函数签名是**待制作内容包的明确建议**，不表示文件已经存在或程序已经冻结。所有输入为合成文本／合成路径，不读取宿主真实 `.env`、配置或凭据。
- 十项只读任务 `allowed_paths=[]`，即使要求回答里包含可运行 Python 示例也不接受候选代码检查点。TK-C01/C02/C03 可采用“唯一 Python fenced block＋指定函数”提取，必须原生执行实际示例，不能只匹配关键词。
- 只读语义 rubric 引用公开源码、已消费材料和真实程序结果；没有候选文件时，不给空 evidence 规则加 `allow_candidate_evidence=true`。TK-D01 的隐藏输入在实际披露消费前不能无条件成为 review source_evidence 或具体正确答案。
- 默认入口只选业务任务；TK-S03/S04 可另设 `diagnose_only` 和 `modify_direct`。两个 modify 首问均完整自足，故 **requires=[]**，不能仅因路线排列在 diagnosis 后便伪造 answer 依赖。二者处于不同场景，各自从原版开始，**无 code 依赖、互不累计**。
- 唯一建议的真实 answer 依赖为 TK-P01 → TK-D02：P01 明确要求基于已接受的方言诊断制定消费者策略，其入口必须同时选 D02；不允许单独选择一个缺前置结果的 P01。其余十一个任务无强制 answer/code 依赖。
- 下列每项都说明材料状态。除 TK-D01 外不另造“无材料”分支：这些任务的定义输入应完整固定，文件漏打包属于内容／准备错误，不应借模型的 `insufficient_information` 掩盖。

### 5. TK-S01：配置编辑接入与局部保真

#### TK-U01｜understand｜理解 TOMLKit 的文档树与保真边界

- **中文用户问题／goal**：这个项目与普通 dict 或标准库 TOML 读取有什么区别？适合编辑配置到什么程度？
- **English prompt**：`Explain how this pinned TOMLKit checkout parses, represents, edits, and serializes a TOML configuration. Distinguish semantic values from retained layout and comments, explain the roles of TOMLDocument, Table, InlineTable, Array, and Trivia, and state the documented layout-preservation limit. Do not edit files or claim every possible mutation is byte-preserving.`
- **公开／隐藏材料**：`materials/editor-context.md` 给单进程人工配置编辑背景、README 和合成含注释／日期／数组文档；隐藏材料无。无需二次索料。
- **正常结论**：`understood`；指向真实 parse／Container／Item／as_string 路径，区别 unwrap 丢样式与文档编辑保样式，明确库不自动校验业务 schema、不提供文件事务。
- **正常／反例独立验收**：可信脚本原生无修改往返保留冻结字节、unwrap 的日期／数组类型符合原始字面；语义评审核解释。反例为将 dict／JSON 重新编码误称保留全部 Trivia，或无条件承诺 README 明示的 AoT 后置子表物理位置不变；原生事实不能独自证明回答质量。
- **allowed_paths／依赖**：`[]`／`[]`；无材料入口不配置。

#### TK-C01｜consult｜用现有 API 保留注释并安全替换字面字符串

- **中文用户问题／goal**：改配置端口和名称，怎么保留评论与原单引号？新值含单引号怎么办？
- **English prompt**：`Using existing public APIs only, provide exactly one complete Python fenced block defining update_config(source: str, name: str, port: int) -> str. Update the supplied name and server.port while retaining untouched text and comments. Keep the original single-line literal quoting when the new name fits it; otherwise fall back to a valid basic string with the same semantic value. Explain why assigning a plain str alone does not promise preservation of the old quote style. Do not modify library files.`
- **公开／隐藏材料**：`materials/leaf-edit.toml` 内容为 `# 配置\nname = 'old' # owner\n[server]\nport = 5432 # port\n`；`materials/leaf-edit.md` 明确 name 本次原始为单行 literal、port 是已有整数，额外未触及字段必须保留。隐藏材料无；无需索料。
- **正常结论**：`usable_example`，既有 API 足够，无需新增 preserve_style 参数；可用 `tomlkit.string(..., literal=True)`，不可表示时使用 basic string。
- **正常／反例独立验收**：提取示例，真实调用 `update_config`，字面期望端口与名称由可信请求生成；普通 new 名称输出仍 `'new'`，中文、反斜杠保语义，原两类注释／未触及字节不丢。含 `'` 或换行的新值必须有效 basic 表示，标准库按 1.0 交集重读严格同值。整体 unwrap→dumps 的例子丢评论应失败；`escape=False` 拼原始引号制造非法 TOML 应失败。本次实测安全 literal 替换及端口更新字节正确；fallback 矩阵待正式 oracle 校准。
- **allowed_paths／依赖**：`[]`／`[]`；不配置无材料分支。

#### TK-C02｜consult｜准确编辑带点的字面配置键

- **中文用户问题／goal**：`io.containerd.grpc.v1.cri` 是一个插件名，为什么按点切路径找不到？怎样只更新其镜像？
- **English prompt**：`The supplied configuration uses [plugins."io.containerd.grpc.v1.cri"]. Provide exactly one complete Python fenced block defining update_plugin(source: str, image: str) -> str that updates only its sandbox_image. Explain literal string keys versus dotted-key construction in this version. Use public existing APIs, retain unrelated plugins and comments, and do not add a new path-query API or modify the library.`
- **公开／隐藏材料**：`materials/plugins.toml` 有完整引用键、目标镜像和另一个插件，另含一个真正嵌套 `plugins.io.containerd` 对照；隐藏无，不依赖调用者未知目录结构。
- **正常结论**：`usable_example`／无需改库；以完整字面 `doc['plugins']['io.containerd.grpc.v1.cri']` 索引，不能盲 `split('.')`。`key('a.b')` 为字面 quoted key，`key(['a','b'])` 才是 dotted key。
- **正常／反例独立验收**：运行真实示例，用独立预期 dict 和标准库 1.0 交集重读核仅指定镜像改变；真实 nested 对照及相邻插件不变，目标镜像中的中文、空白、引号按原生字符串合法编码。反例为误改 nested `plugins.io` 或重建整文档丢评论；缺目标时应保持真实 KeyError 类异常，不静默新建另一条路径。本次微复现字面路径更新及两种 key 构造输出已核。
- **allowed_paths／依赖**：`[]`／`[]`；不配置无材料分支。

### 6. TK-S02：解析失败与方言兼容

#### TK-D01｜diagnose｜材料不足时先索取最小解析证据

- **中文用户问题／goal**：只知道配置报 ParseError，能直接说库有 BUG 吗？
- **English prompt**：`Our configuration loader raises ParseError. I have not provided the exact TOML, loading call, full error, or runtime version. Assess only what the current evidence supports and request the smallest useful reproducer before claiming a root cause. Do not change files.`
- **公开／隐藏材料**：初始仅 `materials/parse-symptom.md` 上述症状；隐藏 `disclosure/parse-reproducer.md` 才提供准确 `port=1\nport=2\n`、完整 parse 调用、原始异常和固定版本。只在明确请求原文／复现等必要证据后披露。另设 `unavailable` 入口公开 `disclosure/parse-unavailable.md`，业务明确拿不到原文／日志，同一任务不另计数。
- **正常结论**：可提供分支，先求证再定位当前示例重复定义键，结果 `no_change_needed`；不可提供分支为 `insufficient_information`，列最小证据和条件假设即可。尚未披露时，不得由隐藏 duplicate-key 事实反向评分“必须已经说出重复 port”。
- **正常／反例独立验收**：消费后原生 parse 真实报 `ParseError: Key "port" already exists. at line 2 col 0`；去掉重复定义正常。不同非法字符串和合法单键对照说明症状不是唯一根因；无材料分支不运行隐藏 reproducer、不接受肯定复现或直接补丁。提供后仍无限追问也不通过。
- **allowed_paths／依赖**：`[]`／`[]`；`unavailable` 只选 TK-D01，避免后继读到未提供的材料。

#### TK-D02｜diagnose｜解释 TOML 1.1 文件与 Python 3.12 消费者差异

- **中文用户问题／goal**：同一配置 TOMLKit 能读，Python 3.12 的 tomllib 不接受，是谁解析错了？
- **English prompt**：`The pinned TOMLKit reads the supplied configuration containing v = "\e", while Python 3.12 tomllib rejects it. Explain the dialect boundary using the actual code and declared TOML support. Verify an equivalent TOML 1.0-compatible spelling and state whether this evidence justifies patching either parser. Diagnose only; do not modify files.`
- **公开／隐藏材料**：`materials/dialects.toml` 准确字节包含反斜杠 e，`materials/dialect-reproducer.py` 两解析器的完整调用、Python3.12约束及 README 1.1 声明；隐藏无。实际 JSON prompt 构造须保留反斜杠，不把它提前变成 ESC 控制字节。
- **正常结论**：`no_change_needed`；固定库支持 1.1 的 `\e`，Python3.12 tomllib 支持1.0，改写为 1.0 的 `\u001b` 可保语义。这不是仅凭两解析器结果不同就认定库有 BUG。
- **正常／反例独立验收**：原版 TOMLKit 得 U+001B，当前宿主3.12 tomllib 对 `\e` 失败；`\u001b` 两者同字符。另以1.1多行 inline／末逗号区分方言，不能删字符假装转换成功。反例包括声称 TOMLKit 仅1.0、把标准库拒绝所有1.1合法输入当本库失败，或对同样1.0非法的重复键也用“方言差异”放过。当前目标3.12.15还需重测。
- **allowed_paths／依赖**：`[]`／`[]`；无材料入口不配置。

#### TK-P01｜plan｜规划兼容旧消费者的配置发布

- **中文用户问题／goal**：编辑端支持1.1，运行端还用Python3.12，怎么避免发布到不能读的配置？
- **English prompt**：`Using the accepted dialect diagnosis, plan a configuration publishing flow for a TOMLKit editor whose downstream consumers must remain on Python 3.12 tomllib. Address pre-existing human-authored TOML 1.1 syntax, generated values, validation before replacement, and preserving semantic values. State the limits of format preservation during explicit conversion. Provide a plan only; do not invent an existing TOMLKit version= or toml_version= parameter or implement a new converter.`
- **公开／隐藏材料**：`materials/publish-requirements.md` 固定消费者3.12、人工文件可能1.1、改动须评审、失败不能发布；隐藏无。使用 TK-D02 已接受答案作为业务输入。
- **正常结论**：`plan_ready`；区分读入保留既有1.1语法与新生成值，选择拒绝不兼容输入或明确授权转换，发布前用实际消费者检查，保真／转换权衡和失败处理清楚。
- **正常／反例独立验收**：可信模型以 `\e` 与 `\u001b`、合法普通文档、重复键分别在两解析器实际运行形成事实；语义评审核方案是否匹配这些事实和失败策略。反例为声称 `dumps(sort_keys=True)` 自动降级方言、全局替换转义可能误改 literal string／评论，或接受后再验证而覆盖旧配置。方案任务不凭事实脚本通过就等同于已实现发布器。
- **allowed_paths／依赖**：`[]`／`[{"task_id":"TK-D02","artifact":"answer"}]`，与 `orchestrator/project_scenario_content.py:177` 的真实字段一致；所有 P01 入口包含 D02。

### 7. TK-S03：数组扩容一致性

#### TK-D03｜diagnose｜定位数组原位重复与序列化不同步

- **中文用户问题／goal**：配置数组乘二后内存是四项，为什么写出来还是两项？
- **English prompt**：`With the complete supplied reproducer, an Array referenced from a document is repeated in place. Its Python values change but dumps still shows the old values. Locate the exact split in representations, compare *= 0, *= 1, and *= 2, and give a bounded caller workaround for doubling using existing APIs. Diagnose only; do not edit library files.`
- **公开／隐藏材料**：`materials/array-reproducer.py` 绑定 `a=doc['a']; a*=2`，输入 `a = [1, 2]\n`，实际内存及输出；隐藏无，无缺失必要前提。
- **正常结论**：`diagnosed`；Array 的 list 与 render/index 片段失同步，继承的 list.__imul__ 绕过维护通道；不是 Python 列表值没有变化。有限 doubling 可用 `a.extend(tuple(a))`，快照防止边迭代边增长。
- **正常／反例独立验收**：原版原生 *=2 为逻辑 `[1,2,1,2]`、文本 `[1,2]`；*=0／负数逻辑空但文本未清，*=1两者一致。调用方 snapshot+extend 实测同一绑定对象和文本均四项；无快照 `a.extend(a)` 的例子不宣称对当前 MutableSequence 迭代安全。反例还包括将整数／浮点 Item 的乘法一概说成相同缺陷。
- **allowed_paths／依赖**：`[]`／`[]`；不配置无材料分支。

#### TK-M01｜modify｜让 Array 原位重复同步全部表示

- **中文用户问题／goal**：修复 Array 的 `*=`，保留文档绑定、合法格式和现有数组操作。
- **English prompt**：`Fix in-place repetition for Array in the supplied reproducer. The same Array object must remain bound to the document, and its values, index operations, unwrap, and serialized TOML must agree after valid repetition counts. Follow Python list index-count semantics, preserve exact text for *= 1, and retain existing comments and the behavior of unrelated array operations. Changes to formatting may be local to material newly added or cleared by repetition. Include regression tests within the allowed paths.`
- **公开／隐藏材料**：完整 array repro、`materials/array-repair.md` 明确乘数0／负数清空，1不改字节，2／3重复；有效 index 整数对象／bool 按Python语义，非index类型失败且原数组不变；有限、无循环、合法可表示值。隐藏只有私有 oracle 和参考实现，不隐藏业务契约。
- **目标与兼容边界**：修 Array 即可；不修改 `_CustomList` 以顺带改变 AoT；保持 array 对象身份与绑定，重复可变元素沿 Python list 的引用语义，不能重建一个脱离文档的新数组。保留 *=1 的所有字节，n>1 不要求把每条评论复制 n 次，但原有评论至少保留且结果有效；n<=0 清除数组内容，外部 key／行尾注释不丢。超大次数、循环对象和预先非法模型不在本任务保证范围，不额外发明静默截断。
- **正常独立 oracle**：可信程序从独立 Python 值构造 `expected = original_values * operator.index(count)`，在0／负／1／2／3、bool、自定义 __index__、空数组、单行／多行带注释、嵌套数组和 inline 值上比较逻辑、unwrap和1.0交集标准库重读；核 `result is original is doc['a']`。随后 append／替换／删除与重序列化必须继续一致。重复嵌套可变元素的引用行为须和 Python list 一致，不能只比第一次输出。
- **反例与冻结上游**：拒绝只更新 list／只更新文本／返回新对象的候选；非法乘数 TypeError 时值与字节不变；未触及数字算术与其他数组编辑照旧。上游当前没有 Array imul 覆盖，`tests/test_items.py:1505` 附近的 `*=` 是 Integer／Float 数值回归，必须保留。原版失败已实复现，参考修复／完整冻结原生回归尚未执行，不预报通过。
- **allowed_paths／依赖**：`library/tomlkit/items.py`、`library/tests/test_items.py`；`requires=[]`。TK-S03 的 `modify_direct` 仍给同样完整材料；不依赖 S04 修改。

### 8. TK-S04：inline 点分字段删除

#### TK-D04｜diagnose｜解释删除最后叶子后的空表和分隔符错误

- **中文用户问题／goal**：删除 inline 配置的最后子字段后，为什么出现两个逗号，甚至空父表消失？
- **English prompt**：`After deleting only t.b.c from the complete supplied inline-table example, the logical tree still contains b = {}, but rendering is invalid or omits that empty parent. Explain the rendering path and distinguish deletion of a leaf from deletion of its parent. Do not modify files or silently redefine empty-parent retention.`
- **公开／隐藏材料**：`materials/inline-delete-reproducer.py` 输入 `t = {a="", b.c=1, d=1}\n`、目标 delete、逻辑和文本实际输出；业务明确删除 c，不删除 b。隐藏无。
- **正常结论**：`diagnosed`；空 dotted Table 仍是键节点，_render_dotted 返回空片段但外层计为已输出键／分隔符；不能归咎于普通 flat inline 删除仍未支持。
- **正常／反例独立验收**：原版中间位置输出 `t = {a="", , d=1}\n`，标准库失败；仅 `t={b.c=1}` 删除后渲染 `{}` 而逻辑仍有 `b={}`，说明即使文本有效也可能丢语义。非最后子字段、普通顶层字段删除为正常对照。答复必须区分三者，不以“清空所有父表是正常清理”代替用户要求。
- **allowed_paths／依赖**：`[]`／`[]`；不配置无材料分支。

#### TK-M02｜modify｜保留删空的 dotted 子表并修复 inline 分隔

- **中文用户问题／goal**：删除叶子时保留仍存在的空父表，不影响普通 inline 删除的既有排版。
- **English prompt**：`Fix inline-table rendering after deleting the last leaf of a dotted child. Deleting the leaf must retain every still-present parent as an explicit empty inline table at the correct path, and the result must parse to the independently expected logical tree. Preserve ordinary flat-key deletion output, untouched documents, sibling values, ordering, and existing dotted-child insertion. Keep the change limited to the allowed paths and add regression coverage.`
- **公开／隐藏材料**：完整 inline repro、`materials/inline-repair.md` 把“保留逻辑空父表、不得擅删”作为明确需求；隐藏仅参考／私有测试。
- **目标与兼容边界**：目标是 InlineTable 的空 dotted 渲染和所需分隔，局部重新表示允许，如 `b = {}`；不重写 Container 删除模型，不改变普通虚拟表在文档级的规则，不扩为所有代理／空容器问题。真正 `del doc['t']['b']` 仍删除整个父键；显式删除与删除其最后叶子不能混同。
- **正常独立 oracle**：可信预期树在操作前独立构造，删除叶子后明确含 `b={}`；首／中／尾／唯一 dotted 子树、多级 `b.c.d`、quoted key、两子树同时清空、显式原有 `{}`、先删后加均检查 stdlib 1.0交集解析结果及逻辑 expected，尤其单子树文本可解析但丢 b 的反例。不能只拿候选自己的 unwrap 给自己作裁判。
- **反例与冻结上游**：普通 flat 删除的五个精确输出 `tests/test_items.py:1232` 起必须逐字保留；`test_deleting_inline_table_middle_element_does_not_leave_double_separator`、已有 dotted 追加两测试全部保留；无修改文档逐字往返、相邻字段／注释不丢，非法重复键仍拒绝。不得“修复”为整体 unwrap 后重新 dumps，也不能删除空父键让自比对通过。当前上游未发现要求删除最后 dotted 叶子后隐式丢父表的冲突断言；这是源码和相关 tests 的核对结论，最终仍须完整上游回归证实。
- **allowed_paths／依赖**：`library/tomlkit/items.py`、`library/tests/test_items.py`；`requires=[]`。TK-S04 有 `diagnose_only`／`modify_direct`，与 M01 分属独立场景，不累计代码。

### 9. TK-S05：编码扩展与写盘边界

#### TK-C03｜consult｜使用既有编码器并限定进程全局影响

- **中文用户问题／goal**：导出含 Path 值的配置，现有 API 能处理吗？怎样避免给后续导出遗留规则？
- **English prompt**：`Use existing APIs to encode supplied pathlib.PurePath values as TOML strings. Give exactly one complete Python fenced block defining render_artifact(path) -> str, including cleanup when encoding succeeds or raises. Explain that encoder registration is process-global and that a try/finally cleanup is not concurrent isolation. Unsupported types must still fail rather than being blindly stringified. Do not modify TOMLKit or read the filesystem.`
- **公开／隐藏材料**：`materials/encoder-context.md` 给单线程一次导出、合成 `PurePosixPath('build/报告.toml')`；异常也要恢复已有规则，不承诺并行隔离。隐藏无；不使用真实配置／路径内容。
- **正常结论**：`usable_example`；register_encoder／unregister_encoder 已存在，返回 `tomlkit.string(...)`、非目标抛 ConvertError，finally 仅移除自身函数。不把 register_encoder 新建为修改任务。
- **正常／反例独立验收**：原生执行回答例子，标准库重读得到路径字符串；调用前／成功后／失败后完整 CUSTOM_ENCODERS 对象序列一致，预置可信其他编码器不被删除，object() 仍 ConvertError。真实 PurePath 不访问文件系统；Unicode／反斜杠合法编码。并发安全结论须语义评审，不把 finally 误判成每文档局部编码器。原版微复现 PurePosixPath 在注册前后均 ConvertError、注册期间正确导出、finally 后 registry 完全恢复。
- **allowed_paths／依赖**：`[]`／`[]`；不配置无材料分支。

#### TK-P02｜plan｜规划配置写入、失败恢复与协作冲突

- **中文用户问题／goal**：工具修改配置时如何保留换行，避免写失败破坏旧文件和覆盖同事改动？
- **English prompt**：`Plan a local configuration editing workflow around the actual TOMLFile API. Preserve existing LF, CRLF, or mixed line endings, prevent partial writes from replacing the original, and detect stale edits among cooperating writers. Distinguish atomic replacement, conflict detection, and crash durability. Specify caller-side responsibilities and a test plan; do not implement the feature or invent existing atomic=, expected_digest=, or lock parameters on TOMLFile.write.`
- **公开／隐藏材料**：`materials/file-edit-requirements.md` 固定同一本地普通文件、合作写入者、仅调用方增强、错误要保旧字节；源码 TOMLFile 和已有换行测试公开；隐藏无，路径均合成。
- **正常结论**：`plan_ready`；既有换行读取／写入可用，当前 write 不提供原子发布或陈旧版本检查。建议调用方同目录暂存、完整序列化／校验、明确权限与清理、合作锁覆盖检查与替换，说明摘要单次检查存在竞争、atomic replace 不等于断电持久性；不要求本轮改库。
- **正常／反例独立验收**：可信事实脚本在临时合成目录对真实 TOMLFile 核 LF／CRLF／mixed 与 PathLike，核真实签名无上述参数；这些文件副作用将在实现验收阶段运行，本次仅读源码与已有 tests，未伪称实测。语义评分依据正常编辑、写入失败、replace失败、A读后B改及不合作写入者等状态表。反例为先 truncate 原文件再谈回滚、只看mtime宣称可检出全部冲突、将“摘要检查→未锁替换”宣称无竞态，或把原子替换等同持久落盘。
- **allowed_paths／依赖**：`[]`／`[]`；无材料入口不配置。

### 10. 本次原版微复现与历史证据

本次两次只读原生微进程使用宿主 **Python3.12.3**，`PYTHONPATH=S`、`PYTHONDONTWRITEBYTECODE=1`、`python3 -B -`，均退出0。实际 `tomlkit.__file__` 为 `S/tomlkit/__init__.py`；只操作内存 TOML／synthetic PurePath，没有改源码或写业务文件。

| 操作 | 本次实际观察 |
| --- | --- |
| Array *=0／-1／False | list 为空，但文本仍 `a = [1, 2]\n` |
| Array *=1／True | 值与文本均保持；对象仍原绑定 |
| Array *=2（含带评论多行输入） | list 四项，但文本仍原两项；对象仍原绑定 |
| Array *=2.0／'2' | TypeError；值和字节不变 |
| 绑定 Array.extend(tuple(Array)) | 对象身份保持，文本与 unwrap 均四项 |
| inline dotted 最后叶子删除，位于首／中／尾 | 分别含前置逗号／重复逗号／残留逗号；1.0标准库失败 |
| 仅一个 dotted 子树删最后叶子 | 输出 `t = {}\n`，可解析但逻辑含 b={}，语义已丢 |
| dotted 子表仍有另一叶子 | 文本有效，剩余 `b.e=2` 在正确路径 |
| `v = "\e"`、多行 inline＋末逗号 | TOMLKit 原版接受，宿主3.12 tomllib拒绝 |
| 单引号 String 显式替换＋端口赋值 | 原评论、未触及布局保留，目标语义正确 |
| 带点插件名索引 | 按完整字面可正确更新；key('a.b') 与 key(['a','b']) 输出确有区别 |
| parse `port=1\nport=2\n` | ParseError，重复 port，line2 col0 |
| PurePosixPath 自定义编码器 | 注册前／卸载后 ConvertError；注册期间真实输出正确，unknown类型失败；全局表在 finally 后与原表相等 |

历史 `.deploy/github-100-research/cli-config/tomlkit/baseline-result.json` 和 XML 记载：Python3.12.3，1203 passed／0 failed／0 error／0 skipped，2.481457519 秒，maximum_rss_kib=55020。XML 本次重读按文件对账：test_api201、test_build4、test_items106、test_parser94、test_toml_document92、test_toml_file8、test_toml_tests680、test_types4、test_utils7、test_write7。最后一类680与固定外部语料相符。

历史安装 3.145 秒、venv 45,946,506B；RSS 是该历史子进程观测口径，不能拿来断言本轮候选 CLI 总资源或目标镜像当前内存。原 `before-submodule-baseline-*` 失败证据保留，说明未展开语料的 collection error 已在历史解决；当前目录语料再次未展开，不能引用历史成功掩盖当前准备条件。

### 11. 实施阶段离线与回归建议

- 根包 `package='tomlkit'`、默认 `implementation_dir='tomlkit'`、`import_root='.'`，原生导入来源必须在受控临时树，不能安装 PyPI 包替代候选。
- 核心无第三方运行依赖。固定 pyproject 的 dev 组有 `pytest~=7.2`、`pytest-cov~=4.0`、`PyYAML~=6.0` 以及文档／类型／提交工具；本批原生 pytest 源码只导入 pytest，无必须第三方 fixture／额外 plugin，没有 pytest addopts 要求 coverage。
- 建议沿源约束冻结 `pytest==7.4.4` 及其当前目标兼容精确依赖，可信 suite `args=['tests','-q','-ra','-p','no:cacheprovider']`、`plugins=[]`、`overlay=True`。pytest-cov／PyYAML 属历史安装环境和上游开发组事实；若正式环境保留它们也须逐 wheel SHA 固定，但不应伪造为本组测试不可缺少的插件。Poetry／poetry-core 用于构建，不需要为了原生 PYTHONPATH 运行完整 Poetry 工具链。
- 只新增 TOMLKit 套件和其私有 wrapper 副本；旧六仓源码／环境／私有回归脚本保持原字节。当前主 wrapper 的布局校验可复用，无需为本仓重做调度、接口或导入模型。
- 必须先在实际 account 镜像 `ci-39609484070-1`、精确 Python 补丁版本（首批实测3.12.15，**本仓尚未重核**）重收集非空完整节点并执行原版，冻结版本／plugins／baseline digest／全部 nodes，而非硬写历史1203。保留适用外部1.1全部语料，不能让1.0标准库当全库1.1合法性裁判；本批业务小样选1.0交集时才可使用 tomllib 独立对照。
- 工程目标分别验证原版失败、独立参考通过、错误候选反例、完整适用上游集合。候选新增 tests 是交付审查材料，可信回归从 baseline 恢复的 tests＋冻结 oracle 才是验收依据。
- 业务预算可先规划30s／256MiB／PID64，完整回归先规划90s／256MiB／PID64；这些仅待校准值，不能因历史2.48s就预写 verified。真实镜像离线安装、业务和回归均须各自测量后再写 profile。
- 全默认任务＋TK-D01正常披露／unavailable、两个direct modify、两个diagnose_only的必要路径纳入后续真实产品链路mock。默认五场景12唯一任务和额外路径分别计数；只读10项没有代码接受，两个独立modify各有自己的接受来源。

### 12. 文件清单与相关规范

| 路径 | 一行说明 |
| --- | --- |
| `.trellis/tasks/10-22-project-catalog-second-pack/prd.md` | 本子任务R1～R10及AC1～AC6，第二批四仓边界 |
| `.trellis/tasks/10-21-project-catalog-expansion/prd.md` | 母任务10项目、150～200任务目标及计数／准入边界 |
| `.trellis/tasks/10-21-project-catalog-expansion/research/document-candidates.md` | 旧文档候选和TOMLKit来源／子模块未展开事实 |
| `.trellis/tasks/10-21-project-catalog-pilot-pack/research/integration-report.md` | 首批6／26／57和真实模型／模拟／部署分开口径 |
| `research/github-projects/tomlkit.md`、`tomlkit-roadmap-20.md` | 历史研究、原版现象及待提案增强，不是新内容完成状态 |
| `.deploy/github-100-research/cli-config/tomlkit/` | 历史安装、原生XML、准备失败、观察脚本及结果，原证据本次未修改 |
| `S/pyproject.toml`、`LICENSE`、`.gitmodules`、README、docs | 固定版本、依赖、许可、语料和原生文档 |
| `S/tomlkit/{api,items,container,parser,toml_file,exceptions,_types,toml_document}.py` | 本批真实函数／类与序列化、文件语义 |
| `S/tests/{test_items,test_toml_document,test_toml_file,test_toml_tests,test_api}.py` | 兼容断言、完整外部语料入口和原生用法 |
| `orchestrator/project_native_regression.py` | 复用的固定回归suite、导入绑定和候选叠加契约 |
| `project_library/projects/tinydb/project.json`、`environments/tinydb-py312/profile/profile.json` | 现有 allowed_paths 带 library 前缀、环境业务／回归分离的实际结构 |

相关规范已读取 `.trellis/workflow.md`、`.trellis/spec/vibecoding-bench/backend/index.md`、`project-iterations.md`：内容schema2／policy3、真实仓逐项准入、英文模型输入／中文公开投影、材料消费隔离、只读候选证据限制、真实同场景依赖、离线版本与完整冻结回归。研究角色隔离规则要求不读取 implement/check JSONL；主会话已确认直接读取这几份事实来源即可。

外部一级来源：

- [主仓固定 tree API](https://api.github.com/repos/python-poetry/tomlkit/git/trees/eddd27e43a62fe58707c311bfad2f52e72493f53?recursive=1)、[固定项目定义](https://raw.githubusercontent.com/python-poetry/tomlkit/eddd27e43a62fe58707c311bfad2f52e72493f53/pyproject.toml)、[固定 LICENSE](https://raw.githubusercontent.com/python-poetry/tomlkit/eddd27e43a62fe58707c311bfad2f52e72493f53/LICENSE)。
- [子模块固定归档](https://codeload.github.com/BurntSushi/toml-test/tar.gz/08ed8697864548b3cdb4b8decbf496bef47e1c82)、[固定 LICENSE](https://raw.githubusercontent.com/BurntSushi/toml-test/08ed8697864548b3cdb4b8decbf496bef47e1c82/LICENSE)、[固定1.1列表](https://raw.githubusercontent.com/BurntSushi/toml-test/08ed8697864548b3cdb4b8decbf496bef47e1c82/tests/files-toml-1.1.0)。
- [TOML1.1官方规范](https://toml.io/en/v1.1.0)：新增escape和inline格式的一级依据；[Python3.12 tomllib官方文档](https://docs.python.org/3.12/library/tomllib.html)作为实施时复核入口，本次web对该URL访问失败，当前1.0差异已用本地3.12实际行为及固定TOMLKit README核实，不从搜索摘要补事实。

## Caveats / Not Found

- 本报告是 **5 场景／12 任务的研究建议**；正式 materials、rubric、manifest、私有 oracle、参考修改、wheel、目标镜像 profile 均尚未创建或通过。不将建议数量直接计入正式十项目目录。
- 本次主仓82 blob已匹配官方固定tree；外部归档1,042 blob也逐项匹配固定子模块官方tree，清单完整，但未写入本地固定检出。不能把来源逐字节核对当作完整适用测试已经运行。
- 两项目标缺陷已在原版当前固定源码复现；窄改是否同时满足全部 frozen upstream 测试，要由正式参考校准证明。特别是 flat inline 删除既有精确字节不能因修 dotted 空表而改变。
- 宿主微复现／历史1203并不等于当前镜像实测。**待当前镜像完成原版完整回归、每个参考业务与完整回归、坏候选反例、离线安装和资源校准后，才可把本仓标为准入通过。**
- 未调用真实模型或OAuth，未修改上游、正式库、其他任务、规范、Git状态或线上环境；未运行昂贵完整回归。语义评分质量和真实token成本仍未知。
