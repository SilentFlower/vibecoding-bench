# Pydantic Settings：真实使用场景样板

## 状态、版本与证据

这是**设计草案**：5 个业务场景、7 个独立计分任务，未运行待测模型、未冻结新验收、未实施修复或增强。任务数量来自业务需求；条件追问、失败重试和检查点重跑均不增加任务数。

固定源码为 [pydantic/pydantic-settings@8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930](https://github.com/pydantic/pydantic-settings/tree/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930)，包版本 2.16.1，MIT。业务仅为本地商品整理工具的标题、数量、标签和组件配置。

旧材料：[单仓研究](../github-projects/pydantic-settings.md)、[20 项工程候选](../github-projects/pydantic-settings-roadmap-20.md)、[观察脚本](../../.deploy/github-100-research/resume-app/pydantic-settings/observe.py)、[观察结果](../../.deploy/github-100-research/resume-app/pydantic-settings/observations-result.json)、[基线复用说明](../../.deploy/github-100-research/resume-app/pydantic-settings/baseline-reuse.json)。旧基线为 Python 3.12.3、1256 主项通过、5 普通跳过；本轮只读复核，未重跑。

上述观察证明若干原版事实，**不等于本页新场景已经独立验收，更不等于模型完成**。本页补充输入、边界与验收均须在冻结时实跑；依赖沿用[原环境重建记录](../../.deploy/github-100-research/resume-app/pydantic-settings/requirements-recovered.txt)，不能以当前最新版替换。

源码证据入口：

- [M：SettingsConfigDict、BaseSettings、来源排序、缓存](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)。
- [E：EnvSettingsSource、next_field、explode_env_vars](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)。
- [D：DotEnvSettingsSource 与文件读取](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/dotenv.py)。
- [B：PydanticBaseSettingsSource 与 JSON 解码](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)。
- [U：类型别名和复杂性判断工具](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。
- [T：原生设置回归](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/tests/test_settings.py)、[P：来源优先级回归](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/tests/test_precedence_and_merging.py)。

## 业务场景索引

`BASE` 表示上述原提交；`CP-UNION` 是未来修复验收通过后才生成的检查点，目前不存在。回答依赖只继承必要对话事实，不隐含代码变更。通用规则见[样板总则](./README.md)。

| 场景 ID | 用户目标 | 任务 ID／使用类型 | 起点与真正依赖 |
|---|---|---|---|
| PS-S01 | 判断是否适合工具并完成配置接入 | PS-UNDERSTAND 理解；PS-CONFIGURE 咨询 | BASE；后者回答依赖前者的业务目标，无代码依赖 |
| PS-S02 | 排查数量与配置文件不一致 | PS-PRECEDENCE 诊断 | BASE；独立，无 BUG 场景 |
| PS-S03 | 排查“数量加载失败”的不完整反馈 | PS-TRIAGE 诊断 | BASE；独立，按需披露材料，无其他任务依赖 |
| PS-S04 | 排查并修复字典联合值未解码 | PS-UNION-DIAG 诊断；PS-UNION-FIX 修改 | 两者从 BASE；修复回答依赖诊断，可提供已核验摘要 |
| PS-S05 | 决定本地工具怎样安全刷新配置 | PS-REFRESH-PLAN 方案 | BASE；独立，只讨论，无待实现 API 依赖 |

所有场景独占临时目录和进程，入口执行环境快照隔离，清除继承的配置变量与 `PYDANTIC_SETTINGS_DEBUG`，退出后还原环境和工作目录并清理临时文件。除明确配置的 `.env` 外不读取文件源；不启用 CLI 或远程来源。每场使用独立模型类，调用缓存的场景结束时执行真实的 `settings_clear_cache()`。

用户可见内容只有本场首问、明确开放的源码／样例与按条件披露的补充材料。以下“评测端”事实、预期输出和检查点规则不拼进用户提示；QA 只要求回答问题所需的事实与少量源码依据，不要求长报告。

## PS-S01：为商品整理工具接入本地配置

**计划夹具与隔离。** BASE 只读；临时目录提供需求卡：“本地批量整理商品记录，配置标题和每批数量；目前写死在脚本里”。不预置配置类；源码可读，依赖可本地导入。没有其他场景修改遗留。

**PS-UNDERSTAND，用户首问：**

> 这个项目是干什么的？我们有个本地商品整理脚本，想把工具标题和每批处理数量移到配置里。用它合适吗？接入时哪些事情还需要我们自己做？

**条件追问。** 仅在回答遗漏“业务脚本仍负责什么”时用户追问：“它会替我执行商品整理吗？”这是同一任务的补救回合，保留累计成本。

**评测端。** M 的 `BaseSettings` 在来源收集后调用 Pydantic 校验；配置读取、类型校验与业务处理分开。预期指出适合该配置需求，并说明业务处理和配置何时重建由调用方组织。可提 `.env`、环境或来源定制，但不要求列全部能力。

**验收与结束。** 必须准确说清用途、适配原因和至少一个实际边界，给出可定位的 M 依据；不得杜撰自动文件监听或自动执行商品业务。满足即可正常结束，不需要改码。源码状态仍 BASE。

**PS-CONFIGURE，用户首问：**

> 那给我一个最小用法：默认标题“商品工具”，数量为 2；本地 `.env` 可以配置，运行时环境变量可以覆盖。数量要是整数，读取后让我能交给原来的业务函数。

**计划补充。** 延续前问业务目标，提供临时文件绝对路径；`.env` 写 `APP_TITLE=商品工具`、`APP_QUANTITY=2`，环境仅增加 `APP_QUANTITY=5`。不提供答案代码。模型可输出片段，允许在临时消费端样例试运行，禁止改项目源码。

**评测端。** 合法最小方案使用 `BaseSettings`、`SettingsConfigDict`，字段 `title: str`、`quantity: int`，真实选项 `env_prefix`、`env_file`；中文文件显式 UTF-8 是可接受选择。M 默认顺序是初始化、环境、dotenv、备用文件源、默认值；本夹具未启用 CLI、未传初始化字段或备用文件目录。

**验收与结束。** 片段应能在夹具中获得标题“商品工具”及整数 `5`，撤去变量后得到整数 `2`；不存在的 API、字符串冒充整数、污染真实环境均失败。默认值与文件值恰好相同不能单独证明读过文件，冻结时追加改文件对照。成功停在咨询交付，BASE 不变；此片段执行尚未完成冻结验证。

## PS-S02：配置文件写 2，运行却得到 5

**计划夹具与隔离。** 独立 BASE；提供消费端 `App`：`model_config = SettingsConfigDict(env_prefix='APP_', env_file=envfile)`，必填 `title: str`、`quantity: int`。临时 `app.env` 内容为 `APP_TITLE=商品工具`、`APP_QUANTITY=2`；进程只有 `APP_QUANTITY=5` 这一业务变量，调用是 `App().model_dump()`，无自定义来源或 CLI。

**PS-PRECEDENCE，用户首问：**

> 配置文件里数量是 2，打印出来却是 5。代码、文件、启动环境和输出都在样例里。帮我判断是不是库的 BUG，并告诉我怎样只使用文件里的数量；先别改库。

**条件追问。** 已提供判断所需材料，不安排强制追问。用户若询问“清空变量后呢”，披露预备的清空变量对照结果；它属于该任务验证，不另计分。

**评测端。** 旧 `native_scenario` 已记录标题“商品工具”、数量整数 `5`。M 的 `settings_customise_sources()` 默认环境先于 dotenv，`_settings_build_values()` 按该优先级合并；E／D 是两个来源。该现象是当前正确行为。

**验收与结束。** 必须明确本例不是 BUG，定位 `APP_QUANTITY` 覆盖关系，并给出可行办法：当前进程删除该变量；若业务要求长期文件优先，可显式定制来源顺序并说明影响。不得建议 `_env_file=None` 来“只读文件”，因为它禁用 dotenv。答清即结束；不要求实现来源调整或提修复。只读，源码状态 BASE。

## PS-S03：信息不足的数量读取报错

**计划夹具与隔离。** 独立 BASE，采用 S02 的真实 `App` 定义与文件，另有 `APP_QUANTITY=invalid`。首轮**不开放该消费端文件、变量清单或异常日志**；仅开放项目源码和下述现象，模型不能通过工具提前读隐藏材料。

**PS-TRIAGE，用户首问：**

> 商品工具启动时报配置错误，看起来与数量有关。是 pydantic-settings 的问题吗？

**可披露材料与规则。** 用户确有这些材料，按模型提出的诊断需求提供；要求“最小复现”可一次得到完整资料，不强制问满三次：

- 要模型／配置代码：给出 S02 `App` 定义、文件路径和调用 `App()`。
- 要输入来源／启动环境：给出临时文件两行与 `APP_QUANTITY=invalid`，说明无初始化值、自定义来源及 CLI。
- 要报错：给出旧观察 `12_physical_input_error_names` 对应的 `ValidationError`，`loc=('quantity',)`、输入 `invalid`；精确渲染待冻结时采集。
- 要对照验证：允许在隔离消费端重现，撤去该变量后读取 `2`；对照仍须冻结实跑，不能把本页期望当执行日志。

**评测端。** 首轮确实不能判断根因，正确动作是提出影响判断的具体问题或明确暂定假设，不能直接断定 BUG。材料补齐后，应识别环境高优先级非法整数输入，解释模型字段名和物理变量名不同，提出撤去或修正该变量的最小验证。

**验收与结束。** 至少取得支持结论的必要材料、给出与材料一致的原因及验证办法才通过。“资料不足，请补充”一句、无依据猜安装损坏、拿到完整材料仍循环索要同物均失败。允许一次精准追问后完成；若必要材料无法提供，可有依据结束为“尚不能定位”，但本夹具全部可提供，因此不能以此替代完成。只读，源码 BASE，无修复检查点。

## PS-S04：字典联合值中的空列表变成字符串

**计划夹具与隔离。** 独立 BASE；定义 `UnionValue(BaseSettings)`，配置 `env_prefix='APP_'`、`env_nested_delimiter='__'`，字段 `config: dict[str, list[str] | str] = {}`。只设置 `APP_CONFIG__ITEM=[]`，禁用 dotenv；提供消费端模型、输入及实际输出。旧观察 `01_union_dictionary_decode` 的原输出是 `{'item': '[]'}`。

**PS-UNION-DIAG，用户首问：**

> 商品参数允许写一个字符串或一组字符串。我给 `APP_CONFIG__ITEM` 传了 `[]`，结果拿到的是字符串。样例和输出在这里，请判断原因，指出有关代码，并给一个不改库的临时办法。

**条件追问。** 关键材料齐全，无必须追问。可选用户问“普通 hello 应怎样处理”，要求说明它应保留字符串；该回合仍是诊断任务。

**评测端。** E 的 `next_field()` 对字典返回原始值类型；`explode_env_vars()` 的原始注解分支只调用 `_annotation_is_complex()`，未采用普通字段 `_field_is_complex()` 中的 Union 复杂性判断。B 最终 JSON 解码未在该分支触发。不能误判为 Pydantic 完全不支持联合类型。

**验收与结束。** 定位上述分支差异并区分正常文本和合法 JSON 列表；可建议整个 `APP_CONFIG` 使用 JSON 对象作为临时绕行，但该替代须先验证再宣称跑通。仅指出现象或直接重写用户类型均不足。诊断可独立成功并结束，不自动修复；源码仍 BASE、BUG 仍存在。

**PS-UNION-FIX，显式后续请求：**

> 请修复库里这个字典联合值的分段环境解码问题，并补回归。合法 JSON 字符串列表要得到列表，普通字符串继续保留，默认行为之外别扩需求。

**代码权限与依赖。** 另开 BASE 可写分支，携带核验过的诊断摘要即可；不要求模型先完成其他任务。仅此请求授权改源码与回归测试，禁止仅在消费端绕开问题。提议触点 E／U／B，实际修改以源码证据为准。

**评测端验收。** `[]` 得空列表、`["咖啡","茶"]` 得字符串列表、`hello` 保持字符串；多个键互不覆盖。非法 JSON 可走现有字符串分支，不能一律拒绝。还须冻结验证已有普通 Union、`NoDecode`／`ForceDecode`、`enable_decoding`、非法列表元素和大小写边界，避免盲目全部 `json.loads()`。关注 T 原生回归。

**结束与检查点。** 新增独立行为验收及适用原生回归均通过后才记录 CP-UNION 的实际提交／补丁摘要、依赖与日志；目前不存在。若未来从该检查点继续，原复现应变为列表，不再把“字符串输出”作为正常期待；其他场景仍从 BASE 启动。失败可重试同任务，不新增计数。

## PS-S05：长期运行工具的配置刷新方案

**计划夹具与隔离。** 独立 BASE；采用 S02 的模型和临时文件。消费端先在数量 `2` 时调用 `App.settings_cached()`；改环境为 `8` 后再次调用；再执行 `App.settings_clear_cache()` 并重新调用。旧观察 `19_validated_refresh` 为 `2 → 2 → 8`，实例引用身份与失败保持行为尚未封存。

**PS-REFRESH-PLAN，用户首问：**

> 本地商品工具会运行很久，想让用户改配置后点一下“重新加载”，先看变化，格式错了继续用旧配置。请根据项目现有能力给一个实现方案，说明哪些现成可用、哪些要由我们补；这轮先不写代码。

**条件追问。** 初始要求包括先校验、再切换、保留旧配置，不强制补问。若模型询问引用生命周期，用户答：“旧批次继续用旧快照，新批次经统一入口取新快照；不需要文件监听，也没有跨进程同步。”

**评测端。** M 已有 `settings_cached()`／`settings_clear_cache()`，没有 `settings_refresh()`。清缓存会先丢弃缓存项，不能等同于“候选配置验证成功后才发布”；旧引用不会因清缓存自动改变。可采用消费端持有快照、用普通构造构建候选、校验成功后在受控入口替换，并定义差异与失败反馈；也接受说明成本后的库级提案。

**验收与结束。** 方案须覆盖候选构建失败、提交时机及新旧引用语义，不能把待新增 API 当既有用法。允许明确采用单进程串行刷新方案；用户没有提出并发要求时，不因未设计并发发布而判失败。若方案主动支持并发，再说明相应发布边界。无需实现接口或长篇设计文档，给出可行方案与主要取舍即可结束。只读，代码 BASE，未生成刷新检查点；不是缓存 BUG 修复任务。

## 覆盖、旧路线取舍与冻结待办

| 使用类型／业务结果 | 覆盖任务 | 代码写入 |
|---|---|---|
| 理解项目用途和边界 | PS-UNDERSTAND | 无 |
| 接入用法咨询 | PS-CONFIGURE | 仅临时消费端样例，不改项目源码 |
| 正确判断现有行为无 BUG | PS-PRECEDENCE | 无 |
| 信息不足时提问并完成定位 | PS-TRIAGE | 无 |
| 证据定位真实解析缺陷 | PS-UNION-DIAG | 无 |
| 比较可行方案与兼容取舍 | PS-REFRESH-PLAN | 无 |
| 明确请求后的源码修复 | PS-UNION-FIX | 条件允许，通过后产生检查点 |

旧路线 01 转为“可独立结束的诊断＋显式修复”；19 转为刷新方案任务。正常接入、优先级及信息不足诊断从已有业务事实补出，不冒称工程增强。旧路线其余 18 项保留在候选池，不宣布删除。

暂不收进本样板的两个高相关候选：06 的 TypeAliasType 嵌套模型列表问题已在旧观察复现，但与本轮字典 Union 诊断／修复形成的使用方式相近，后续可作为类型分支扩展；07 的跨来源列表合并适合作为另一类方案题，但当前样板只保留刷新方案，避免为了覆盖需求池而拉长会话。CLI、模板等其余候选也不机械加入。

冻结前须分别落盘消费端夹具、隐藏补充材料、任务可见文件清单、依赖锁定与验收执行器；校验环境恢复、源码版本和真实导入路径。原观察只覆盖部分输入，新列边界和消费端片段必须实跑并保存原始结果。评测端根据已核对的事实独立冻结预期，不从候选自报的结果反推；模型与候选程序不能读取本页隐藏答案。

QA 完成记录答案依据与结论；修改完成另记录代码检查点和行为回归，两者不能互相冒充。按任务类型统计输入／输出／缓存 token、耗时、追问与重试累计成本；本页没有模型结果，不声称场景混合已减少 token。
