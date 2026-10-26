# Research: python-dotenv 第二批内容规划

- Query: 在冻结工程上设计去重的真实理解、咨询、诊断、方案与修改任务，核实插值兼容、文本编辑保真及原生接入条件。
- Scope: mixed；只读源码、上游测试与旧证据，短进程纯内存复现；本文件是规划，尚未制作正式内容或参考实现。
- Date: 2026-10-22

## Findings

### 结论与数量

建议 **5 场景、12 个唯一任务**：understand 2、consult 2、diagnose 4、plan 2、modify 2；10 项非修改。两项修改为“保留非目标记录的原始换行”和“写入前拒绝包含 CR/LF 的键”。`${B:-d}` 空值语义用于诊断与应用方案，**本批不修改其既有全局语义**。披露、无法提供材料、正常对照、修改附带测试都不另计任务。

### 来源、文件与真实接口

- 官方仓库：[theskumar/python-dotenv](https://github.com/theskumar/python-dotenv/tree/0b2880591780a426b0551436f47a17e7a76d954f)，固定提交 `0b2880591780a426b0551436f47a17e7a76d954f`，`src/dotenv/version.py` 为 1.2.4，Python ≥3.10。2026-10-22 官方 commits API 返回的 SHA 与请求完整 SHA 一致；网页抓取受限，未改用第三方来源。
- 本地冻结工程：`.deploy/real-project-review-20261021/python-dotenv-review/source/`。BSD-3-Clause，`LICENSE` 包含原版权及再分发条款，正式 seed 须原样保留。历史规模为47个跟踪文件；本轮未重新打包或创建另一个工程副本。
- `src/dotenv/main.py:42` 的 `DotEnv` 接收 path/stream、interpolate 和 override；`:79` 缓存解析映射，`:101` 只有非 None 值进入进程环境；`:333` 以已经解析的前项和环境构建插值上下文；`:431` 的 `load_dotenv` 默认 override=False，`:482` 的 `dotenv_values` 使用 override=True 且只返回映射。
- `src/dotenv/main.py:162` 的 `rewrite` 读取文本和写临时文件，原子替换并保留既有模式／错误清理；`:224` 的 `set_key` 将目标行序列化为 LF、非目标写回 `Binding.original.string`；`:288` 的 `unset_key` 丢弃匹配记录，写回其余原文。
- `src/dotenv/parser.py:26` 的无引号 key 规则不接受空白；`:42` 的 `Binding` 有 key/value/original/error；`:69` 的 Reader 去除开头 BOM。不能凭文本直觉发明 parser 字段，也不能把“保留换行”扩大为重写 parser 或改变读值时的通用换行语义。
- `src/dotenv/variables.py:64` 的 `Variable.resolve` 使用 `env.get(name, default)`，存在的空值保留为空，存在的 None 转空；不是完整 shell 解释器。
- `src/dotenv/cli.py:143` 的 `get` 将空字符串视为合法输出，裸键／缺失失败；`:193` 的 `run` 默认 override=True，`:213` 使用 argv 和新环境启动实际子进程。`src/dotenv/__main__.py` 直接导出真实 Click cli；pyproject 的脚本定义为 `dotenv = dotenv.__main__:cli`。
- `src/dotenv/ipython.py:34` 的 `%dotenv` 调用 `find_dotenv(..., True, True)`，默认不覆盖，`-o` 才覆盖。IPython 是适用回归依赖，不是核心解析的运行依赖。

### 已核实的兼容事实

本轮用宿主 Python 3.12.3、`python3 -B`、只读冻结源码、StringIO 和 `mock.patch.dict(os.environ, {}, clear=True)` 做纯内存复现；没有调用默认自动查找，没有读取宿主 `.env`，没有写配置文件：

| 调用 | 实际原版结果 |
| --- | --- |
| `Variable('B', 'd').resolve({})` | `d` |
| 同表达式，B为空字符串 | 空字符串 |
| 同表达式，B=None | 空字符串 |
| 同表达式，B=`v` | `v` |
| `dotenv_values(stream=StringIO('B=\nA=${B:-d}\n'))` | B和A均为空 |
| 相同表达式且 interpolate=False | `${B:-d}` 原样 |

已检索完整冻结 `tests/` 的 `:-` 用例。`tests/test_main.py:883` 参数表覆盖缺失与非空默认值，并未发现专门保护 `${B:-d}` 空值结果的断言；**未发现断言不等于没有兼容影响**。`tests/test_cli.py:266` 的 `--no-override` 参数表则明确保护“现有环境值为空也优先、派生值为 `/suffix`”；虽然表达式没有 `:-`，一般空值优先级必须保留。不能把所有空值都当缺失，或为了新题改写上游测试。保持当前语义、在应用指定字段显式补默认值可完成需求，故不选该变化为修改题。

两项修改的原版失败证据已在旧 `reproductions-result.json` 的 `preserve_unedited_crlf`、`reject_unrepresentable_key` 保存；本轮读过原版写入路径，但没有重复写文件复现。实施时必须在当前镜像重新得到原版失败、私有参考通过和反例拒绝，旧研究不能替代准入。

### 材料、评分与依赖的共用契约

- 下列页面标题及 goal 为中文；任务首问、附件指令、分支 when 和私有自然语言 rubric 用英文。下表 User question 是可直接扩展的英文首问，不是中文页面文案。
- 非修改任务统一 `allowed_paths=[]`、不创建代码检查点；回答应引用冻结源码符号。除 DE-D01 外材料初始齐备，无隐藏披露，也不安排人为的“无法提供”分支；若业务另有缺失，允许注明范围但不能猜测事实。
- DE-D01 有正常披露和 unavailable 入口；初始 rubric 只能要求发现信息缺口，不得把未消费的 APP_MODE 环境值提前要求为结论，也不得无条件纳入 source_evidence。unavailable 合法结束为 `insufficient_information`，不是模拟 failure/retry。
- native 断言验证真实 API／CLI 与材料事实，自由文本仍需私有语义评审；不把控制端方案见证当候选自行生成实现，也不以“包含若干字符串”代替答案质量。
- 五个场景独立从同一冻结原版建立工作区。所有任务 `requires=[]`：两项修改已自带完整复现及契约，不需要消费先前诊断回答；默认 D→M 仅是呈现顺序，不虚构 answer 依赖。**没有 code 依赖、没有跨场景修改继承**。直接修改入口须提供相同完整业务附件，不能要求前置会话记忆。

### 场景与任务表

#### DE-S01：把配置加载接入本地应用（3 项）

**DE-U01 / understand / goal：区分解析映射、加载环境与覆盖优先级。**

- User question: `Trace dotenv_values and load_dotenv for the supplied synthetic configuration. Explain which call mutates the process environment, how override affects both final values and interpolation, and which existing values remain untouched. Do not edit files.`
- 公开：`configuration.env.txt` 为 `BASE=file\nDERIVED=${BASE}/data\nEMPTY=\nBARE\n`，`environment.json` 明示 BASE=process；调用片段分别使用 dotenv_values、load_dotenv 默认和 override=True。无隐藏／无 unavailable 分支。
- 合法结果：`explained`；不能把 dotenv_values 返回映射误写成已加载环境，也不能把 True 当“每一个值都被覆盖”。
- 独立正常／反例：隔离进程记录调用前后环境及解析映射；默认 load 保留 process并派生process/data，override=True使用file，dotenv_values用file但不改环境；BARE不注入、EMPTY注入空字符串；已有无关 SYNTHETIC_KEEP 保留。直接导入候选并核 __file__。
- allowed_paths `[]`；requires `[]`。

**DE-C01 / consult / goal：用现有映射 API 选择有序配置合并方式。**

- User question: `We have a shared file, a local file and an explicit deployment mapping. Later layers win. No value refers to another file. Recommend a minimal solution using this version, without adding a multi-file API or mutating os.environ.`
- 公开：三个合成层分别定义独有键和共享 COLOR；明确没有跨文件插值要求、空值有业务含义。无隐藏／无 unavailable。
- 合法结果：`advice_no_code_change`；多个 dotenv_values 结果按顺序合并足够，需说明每文件已解析，合并不会重新执行跨文件插值。
- 独立正常／反例：真实 API 分别读两份临时文件，按层合并产生 COLOR=deployment及各独有键；环境前后摘要同；交换文件顺序产生不同 COLOR，空字符串不被自动忽略。可执行见证证明建议可行，不强制某种文本样式。
- allowed_paths `[]`；requires `[]`。

**DE-P01 / plan / goal：规划显式路径加载及启动校验，避免依赖工作目录猜测。**

- User question: `Plan startup for a local application launched from different working directories. The caller supplies an absolute configuration path; loading must preserve existing deployment values and missing required application fields must stop startup. Use existing APIs and separate application validation from dotenv parsing.`
- 公开：英文 `startup-requirements.md` 给合成绝对路径、必填字段、允许空值字段、外部环境优先和缺文件策略。无需自动递归查找，无隐藏／无 unavailable。
- 合法结果：`viable_plan`；显式路径／返回映射、明确验证后启动，不能发明 strict/start_dir 参数，不能承诺 load_dotenv 的 bool就是业务配置完整。
- 独立正常／反例：控制端见证在两个临时 cwd 使用同一明确路径，得到同配置；必填缺失时应用启动标志文件不存在；允许空字段保留空；不挂宿主父目录，不真正查找宿主 `.env`。
- allowed_paths `[]`；requires `[]`。

#### DE-S02：加载后为什么仍然是旧值（2 项）

**DE-D01 / diagnose / goal：先索取最小配置材料，再区分环境优先级与真实故障。**

- User question: `The application still reports its old mode after dotenv loading. Determine what evidence is missing before choosing a root cause. Request the smallest useful sanitized reproduction, then diagnose only what the supplied evidence supports. Do not edit files.`
- 初始公开：版本与症状，不给调用签名、文件或进程变量。正常请求最小材料后披露 `loader.py`（显式路径、默认 load_dotenv）、`synthetic-config.env.txt`（APP_MODE=local）、`environment.json`（APP_MODE=deployment）、`observed.json`（返回True、值deployment）。文件名、正文均冻结，不用真实环境。
- unavailable：用户无法提供最小调用／环境／目标文件信息时只交付英文说明；合法结果 `insufficient_information`，回答列最小缺口及有条件排查，不断言具体覆盖原因。正常披露后为 `diagnosed_no_code_change`，可建议应用明确选择override政策。
- 独立正常／反例：消费正常材料后真实load默认保持deployment；override=True反例改为local，未设APP_MODE对照加载local；未披露阶段不运行只能凭隐藏配置才成立的必答断言。分支不新增任务或业务尝试。
- allowed_paths `[]`；requires `[]`。

**DE-C02 / consult / goal：区分空赋值、裸键和缺失键的读取结果。**

- User question: `Our export tool must distinguish EMPTY=, a bare OPTIONAL key and an absent key. Explain the mapping and CLI get results, recommend an explicit application policy, and say whether the current library needs a change.`
- 公开：合成 `EMPTY=\nOPTIONAL\n`，需求允许EMPTY、OPTIONAL表示未配置。无隐藏／无 unavailable。
- 合法结果：`advice_no_code_change`；映射EMPTY为空、OPTIONAL=None、缺失无键；CLI get EMPTY为成功空行，裸键／缺失非零，不能把空行当失败。
- 独立正常／反例：实际 candidate API与实际 `python -m dotenv -f <temp> get ...` 对照 stdout/exit；`list --format=json`保留裸键为null而普通list不输出None；真正非空值照常成功。只在受控子进程验证。
- allowed_paths `[]`；requires `[]`。

#### DE-S03：插值顺序与空值兼容（3 项）

**DE-U02 / understand / goal：解释顺序插值、字面量与已有关闭选项。**

- User question: `Explain why A=${B} before B=ready differs from the reverse order, why $B remains literal, and how to preserve all interpolation expressions literally with existing options. Use the pinned parser and resolver; do not add recursive expansion.`
- 公开：两个完整输入流、无同名环境、`$B`、`${B}` 与 interpolate=False调用；无隐藏／无 unavailable。
- 合法结果：`explained`；逐项前向顺序，不承诺Bash执行、递归或 `%B%` 展开。
- 独立正常／反例：受控映射内 A在B前得到空，B在前得到ready；$B原样；interpolate=False全部原样；有外部B时按实际override语义核对。环境清空只在业务子进程。
- allowed_paths `[]`；requires `[]`。

**DE-D02 / diagnose / goal：识别空值默认表达式的既有行为与兼容影响。**

- User question: `For B= followed by A=${B:-d}, A is empty rather than d. Compare missing, empty, bare and non-empty B in this pinned version. Explain the implementation and compatibility implications before calling for a change; do not modify the library.`
- 公开：四个完整StringIO输入与业务预期d，说明是与shell直觉对比，不声称上游已承诺修复；无隐藏／无 unavailable。
- 合法结果：`diagnosed_compatibility_behavior`；准确指出env.get只对缺失选default，None最终变空，保留实际版本观察；不得混淆DE-D01的override原因。
- 独立正常／反例：上述本轮纯内存五种结果在目标镜像复核；缺失和非空是正常对照；`${B}`与interpolate=False不改变。审阅应接受“应用需求不同，但全局改变有兼容代价”。
- allowed_paths `[]`；requires `[]`。

**DE-P02 / plan / goal：为指定业务字段规划显式空值默认政策。**

- User question: `Design an application-level policy where only REGION treats missing, bare and empty input as local. Empty values of other fields must keep their meaning, and derived REGION_LABEL must use the validated region. Preserve python-dotenv's defaults and the source file.`
- 公开：`policy.md` 明确REGION与REGION_LABEL关系、可用dotenv_values(interpolate=False)、其他字段无自动补值、原文件／环境不变。无隐藏／无 unavailable。
- 合法结果：`viable_plan_no_library_change`；应用先解析原值、只为REGION显式合并默认并校验，再生成指定派生字段；不以全局truthiness、全库Variable.resolve变化或shell执行达成。
- 独立正常／反例：控制端见证真实API解析missing/None/empty/nonempty REGION四路，再按明确应用规则生成label；OTHER_EMPTY始终空，原文件与环境摘要不变。不是要求候选实现通用插值器。
- allowed_paths `[]`；requires `[]`，不硬依赖前两题answer，初始资料足够独立完成。

#### DE-S04：配置编辑只改变目标记录（2 项）

**DE-D03 / diagnose / goal：用实际文件字节定位非目标换行被改写的原因。**

- User question: `After set_key updates COLOR, unrelated comments and a multi-line value have changed from CRLF to LF. Explain the read/parse/rewrite path using the supplied before/after bytes, distinguish semantic value changes from file-format changes, and identify the smallest correction. Do not edit files.`
- 公开：before/after十六进制与可读转义、更新COLOR的完整调用、非目标多行值；无隐藏／无 unavailable，不把全文件CRLF截图当充分证据。
- 合法结果：`diagnosed`；定位rewrite的通用换行转换破坏了original.string，而不是dotenv解析必定重新序列化所有键。
- 独立正常／反例：当前镜像原版实际set_key前后字节记录；非目标CRLF丢失、纯LF正常；语义映射对照保持。允许数据值包含中文，但说明仍为英文。
- allowed_paths `[]`；requires `[]`。

**DE-M01 / modify / goal：保留 set/unset 非目标记录的原始换行。**

- User question: `Preserve the original text and newline bytes of every non-target parsed record when set_key or unset_key edits a UTF-8 file. Keep the existing LF serialization of changed or newly appended target lines and the existing return values, quoting, file modes, symlink behavior and failure cleanup. Add focused public tests.`
- 公开：重复提供DE-D03附件、精确“非目标原文”范围；不要求检测主换行、不改变目标行LF、不新增BOM保留特性、不改只读API的换行规范。无隐藏／无 unavailable；原实现已支持BOM读取，既有测试仍须通过。
- 合法结果：`implemented`，真实业务断言及冻结全部适用回归通过，公共测试可读且覆盖目标；不接受只改测试或把目标行改成CRLF后仍损坏旁行。
- 独立正常／反例：CRLF、LF、CR及混合非目标注释／空行／多行值原字节相等；set替换／追加和unset删除分别验证，目标行仍LF；无末尾换行追加只允许既有必要分隔变化，单独列清边界；无关值及返回元组不变，语义读回一致。模式／既有follow_symlinks／失败清理依冻结上游回归保持。原版目标必须失败、参考必须通过。
- allowed_paths `['library/src/dotenv/main.py','library/tests/test_main.py']`；requires `[]`。该场景原版起步，默认诊断在前但无必须消费的answer或code前置，允许自足的直接修改入口。

#### DE-S05：配置表单的键不能跨行（2 项）

**DE-D04 / diagnose / goal：定位跨行键写入成功却无法按原键读回的问题。**

- User question: `Our local configuration editor accidentally passed a line break in a field name. set_key returned success, but the same key cannot be read back. Explain the mismatch between the writer and parser and propose a narrow data-integrity rule; do not change files.`
- 公开：合成键 `REPORT\nREGION`、受控原文件、调用和读回结果；说明普通表单数据错误，不涉及认证或外部系统；无隐藏／无 unavailable。
- 合法结果：`diagnosed`；writer直接格式化键、parser按记录语法读取，拒绝不等于替换／修剪键；不泛化为“全部非ASCII键无效”。
- 独立正常／反例：旧复现记录原版返回成功、文件改变、get_key同键找不到；实施时对LF、CR重做原版对照；`REPORT_REGION`与合法Unicode键必须往返正常。读回过程显式传临时路径。
- allowed_paths `[]`；requires `[]`。

**DE-M02 / modify / goal：跨行键在打开或创建配置文件前明确失败。**

- User question: `Make set_key raise ValueError for a key containing CR or LF before opening the rewrite or creating a destination file. Existing files must remain byte-identical and missing destination files must remain absent on rejection. Preserve normal keys, values, return values and other editing behavior. Add focused tests; do not broaden the accepted-key policy.`
- 公开：重复DE-D04完整例子、现有文件和缺失目标两路、允许改动路径。只约定API异常类型，不固定新错误全文，不要求改CLI异常协议、不改unset_key参数政策。无隐藏／无 unavailable。
- 合法结果：`implemented`；可以内部短校验，禁止静默去换行、截断键、先写后恢复、仅靠parser失败。
- 独立正常／反例：CR、LF、CRLF分别ValueError；用控制端spy核rewrite未进入／临时文件未创建，同时核原文件SHA与目录清单；缺失目标仍不存在。合法下划线、点、连字符、Unicode键保留既有往返；value内换行仍按既有quote模式处理；引号／反斜杠值与合法新文件创建维持。候选自带测试不代替控制端；冻结原生集合保持。
- allowed_paths `['library/src/dotenv/main.py','library/tests/test_main.py']`；requires `[]`。不同于DE-M01，本场景独立原版起步；默认诊断在前但无必须消费的answer，允许自足的直接修改入口；不隐式继承CRLF修复。

### 原生接入、依赖与资源

1. 现有共享runner已支持src布局；本仓应设 `package=dotenv, implementation_dir=src/dotenv, import_root=src`，overlay只叠实现，恢复冻结tests与配置。不能将python-dotenv发行名当模块名，不能误导入环境里pydantic-settings附带的dotenv。
2. CLI必须是实际可执行 `dotenv` 入口，指向目标解释器和受控src候选路径；仅验证 `python -m dotenv --help` 不覆盖上游直接执行dotenv的测试。脚本所在只读挂载须可执行，不能放noexec tmpfs。`tests/test_lib.py` 的subprocess与 `tests/test_cli.py` 的exec路径都须核源。
3. 核心无外部依赖；回归至少需要Click、IPython、pytest及其实际传递依赖。历史冻结有 click8.5.0、ipython9.17.1、pytest9.1.1等，清单见旧test-requirements.txt；不能直接把本仓现有pydantic环境当完整profile。当前镜像精确Python与wheel/hash需重校，IPython的importorskip不能被当主动省略理由。
4. 历史账号镜像 `ci-39482854683-1`、Python3.12.3、UID1000隔离基线 **288 passed，0 skipped/error**，pytest2.973秒，256MiB；宿主root曾因权限跳过4、祖先.env导致4失败，均留原证据。当前目标为主会话指定镜像，不能用历史288硬编码新合同。需完整收集并执行所有适用节点；FIFO／权限测试必须在UID1000、无祖先宿主.env的环境下运行。
5. 建议起点：业务256MiB、10秒；完整回归256～512MiB、30秒，均是待实测建议，准备依赖与业务计时分开。真实资源依据当前镜像观测；无账号HOME、无网络、不读真实配置、不把测试venv放seed。

### 相关规范与证据

- `.trellis/spec/vibecoding-bench/backend/project-iterations.md` 的“内容schema2／policy3”“原生套件布局与校准”“真实GitHub项目逐仓研究”是准入契约。
- 本任务 `prd.md` R1～R10、AC1～AC6；母任务 `research/operations-candidates.md` 后续wave；旧 `research/github-projects/python-dotenv.md`、`python-dotenv-roadmap-20.md` 仅作选题与历史实证，不机械转20步。
- 官方固定源码：[main.py](https://github.com/theskumar/python-dotenv/blob/0b2880591780a426b0551436f47a17e7a76d954f/src/dotenv/main.py)、[variables.py](https://github.com/theskumar/python-dotenv/blob/0b2880591780a426b0551436f47a17e7a76d954f/src/dotenv/variables.py)、[test_main.py](https://github.com/theskumar/python-dotenv/blob/0b2880591780a426b0551436f47a17e7a76d954f/tests/test_main.py)、[test_cli.py](https://github.com/theskumar/python-dotenv/blob/0b2880591780a426b0551436f47a17e7a76d954f/tests/test_cli.py)、[LICENSE](https://github.com/theskumar/python-dotenv/blob/0b2880591780a426b0551436f47a17e7a76d954f/LICENSE)。2026-10-22官方API核对入口为 `https://api.github.com/repos/theskumar/python-dotenv/commits/0b2880591780a426b0551436f47a17e7a76d954f`。

## Caveats / Not Found

- 尚未制作正式manifest、英文附件、rubric、冻结native脚本、wheel profile和两个参考修复；场景与任务数是逐项规划，不是已准入数量。
- `${B:-d}`空值没有发现专门上游断言，但有明确源码行为和空环境优先级测试；本方案选择保留而非暗中改语义。
- DE-M01只保证非目标记录原文；新增／替换目标继续LF，不能把它报告为全文件换行风格继承。BOM原有解析、权限／symlink等适用上游保护不放松。
- 当前镜像全部回归、资源、参考正例与错误候选负例仍待执行；纯内存短复现不替代真实文件业务验收。没有真实模型、OAuth、产品写入、提交或部署。
