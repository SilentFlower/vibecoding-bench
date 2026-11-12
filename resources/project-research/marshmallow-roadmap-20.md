# Marshmallow：二十步原生工程路线

固定 [marshmallow-code/marshmallow@b762ea2d59ca52fe5df76b90de14bed7e5ec5607](https://github.com/marshmallow-code/marshmallow/tree/b762ea2d59ca52fe5df76b90de14bed7e5ec5607)，4.3.1。前四项有固定原版复现，后十六项为源码／现有使用方式对照后的增强提案；未实施，未获上游承诺。原版观察在 `.deploy/github-100-research/core-utils/marshmallow/observations-result.json`。

每步交付实现、文档、正常和边界验收，并累计运行原生 `python -m pytest tests`。源码路径相对src/marshmallow，测试相对tests。新增Field选项须同步_BaseFieldKwargs与类型签名，不另计为一步。已有pre_load/post_load字段处理器、Schema钩子、only/exclude、partial、unknown三政策、from_dict、定制Field、experimental.Context及第三方适配方案保留；不把这些现有能力重新计数。各步独立，新接口名称只是提案。

## 01．邮件域名最后一段拒绝首尾连字符（修复）

- 来源：[官方 #3072](https://github.com/marshmallow-code/marshmallow/issues/3072)，validate.Email的DOMAIN_REGEX。原版接受a@example.-com与a@example.com-，普通a@example.com为对照。
- 交付：末标签与其他域名标签采用一致的边界约束，保留明确允许的localhost／地址字面量；不查询DNS。
- 验收：首／尾／中连字符、单／多标签、IDNA与Unicode现有集合、长度边界；test_validate.py／test_deserialization.py。多种坏域名是同一步。

## 02．Date反序列化不保留datetime时间部分（修复）

- 来源：[官方 #3068](https://github.com/marshmallow-code/marshmallow/issues/3068)，fields._TemporalField对date使用isinstance，而datetime是date子类。实测返回datetime(2026,1,1,3,4)。
- 交付：明确拒绝datetime或仅在显式转换模式下截取date，默认不能返回与Date内部类型不符的值；保留真正date对象。
- 验收：date／datetime／aware datetime、ISO字符串、None政策、自定义date子类；fields.py，test_fields.py／test_deserialization.py。同步类型标注与文档，兼容变化明示。

## 03．POSIX格式的纪元前日期往返（修复）

- 来源：[官方 #3019](https://github.com/marshmallow-code/marshmallow/issues/3019)。DateTime('timestamp')把1969-01-01写为-31536000，utils.from_timestamp却拒绝其原生输出。
- 交付：在平台支持的日期范围内读取负秒／毫秒，与序列化一致；布尔值、越界和无效值仍拒绝。
- 验收：纪元前／零点／正数、UTC与naive政策、毫秒精度、NaN/inf、平台OSError；utils.py／fields.py，test_utils.py／test_deserialization.py。不承诺所有操作系统支持相同最早日期。

## 04．未知输入不覆盖已归一化的已知字段（修复）

- 来源：Schema._deserialize的unknown=INCLUDE追加路径。amount用data_key='externalAmount'，输入合法外部3再附amount='bad'，原版输出amount='bad'，覆盖已通过字段转换的整数。
- 交付：在外部名到内部名／attribute路径多对一冲突时明确报ValidationError，避免静默覆盖；普通互不冲突的未知键仍可包含。
- 验收：data_key、attribute、嵌套路径、相同值也报告歧义、EXCLUDE/RAISE对照、many错误索引；schema.py／error_store.py，test_schema.py／test_deserialization.py。依赖旧覆盖行为的调用方须迁移，不暗称无兼容影响。

## 05．required字段在partial载入时可选默认值（增强）

- 来源：[官方 #2151](https://github.com/marshmallow-code/marshmallow/issues/2151)。当前required和load_default同时提供直接ValueError；partial会跳过缺失字段，不应用这种默认。
- 交付：独立、显式的partial默认策略，全量载入仍要求存在，未启用时保持现有跳过行为。
- 验收：全量缺失、partial=True／字段集合、默认工厂每次调用、嵌套、显式None、已给值；fields.py／schema.py，test_deserialization.py／test_options.py。不能仅移除构造检查后误称默认已生效。

## 06．Meta声明默认partial政策（增强）

- 来源：[官方 #2103](https://github.com/marshmallow-code/marshmallow/issues/2103)。Schema已有构造partial，但SchemaOpts不读取Meta.partial，实测设置后缺必填仍失败。
- 交付：Meta默认、构造覆盖、单次load覆盖的清楚优先级，区分None与False；支持字段集合而非只开关。
- 验收：Meta继承、显式False、部分字段集合、Nested传播、validate与load一致；schema.py:SchemaOpts/Schema，test_options.py／test_deserialization.py。不重计已经存在的构造参数。

## 07．类型转换后、验证前的处理阶段（增强）

- 来源：[官方 #1961](https://github.com/marshmallow-code/marshmallow/issues/1961)。Field已有pre_load在反序列化前、post_load在验证后，中间没有显式pre_validate阶段。
- 交付：处理已经转换的内部值后再运行validators；与现有两个阶段的顺序固定，保留缺失／None短路约定。
- 验收：转换后舍入再范围校验、回调异常、处理链、allow_none、默认值、内嵌字段；fields.py／types.py，test_fields.py／test_deserialization.py。用户自定义Field可替代，不宣称没有其他实现方式。

## 08．钩子的显式顺序约束（增强）

- 来源：SchemaMeta.resolve_hooks遍历dir(cls)，现有钩子没有priority/before/after接口；文档未保证同阶段注册顺序。
- 交付：opt-in优先级／依赖声明，继承覆盖与pass_collection阶段关系明确，发现环在构造时报告；未声明者保留旧政策。
- 验收：多个钩子、父子类、同优先级、未知依赖、环、处理失败顺序；schema.py／decorators.py，test_decorators.py。不是通过重命名用户方法达到隐式排序。

## 09．内置显式标签联合字段（增强）

- 来源：[官方 #1751](https://github.com/marshmallow-code/marshmallow/issues/1751)。核心没有Union字段，已有marshmallow-oneofschema等外部方案及自定义Field。
- 交付：discriminator到已注册Schema的固定映射，双向载入／输出；不动态import类，未知／重复标签明确失败。
- 验收：两种业务记录、标签缺失／错误、嵌套列表、字段级错误路径、only/exclude、many；新增联合字段及test_fields.py／test_schema.py。不得试遍所有schema后随意取第一个。

## 10．PathLike原生字段（增强）

- 来源：[官方 #1815](https://github.com/marshmallow-code/marshmallow/issues/1815)。核心无Path字段，可用自定义Field或post_load手工转换。
- 交付：字符串与pathlib.Path双向转换，默认只处理路径数据，不隐式访问文件系统；可选相对路径／根目录政策明确。
- 验收：中文、空路径、绝对／相对、Windows形式作为数据、PathLike对象、非法类型；fields.py，test_fields.py／test_serialization.py。不能仅把任何对象str化当作合法路径。

## 11．文档集合的惰性逐记录处理（增强）

- 来源：[官方 #1696](https://github.com/marshmallow-code/marshmallow/issues/1696)。dump(many=True)和load(many=True)产出整列表，核心无iter_dump/iter_load；用户可自行逐条循环。
- 交付：逐条转换的有界内存接口，保留记录编号、停止／继续错误政策和生成器关闭；collection级钩子与流模式冲突时明确拒绝或选择批次政策。
- 验收：首项可提前消费、无限输入有限前缀、单条错误、close、partial/unknown、批钩子；schema.py，test_serialization.py／test_deserialization.py。导入与导出共同算这一项流处理能力。

## 12．部分补丁与原数据合并后的完整校验（增强）

- 来源：HTTP PATCH类业务。partial=True只跳过缺字段，不持有旧状态，跨字段约束不能自然验证补丁与旧数据合并后的整体。
- 交付：load_patch(base,patch)先处理显式变更，再按声明合并和完整约束检查，成功才返回新对象；不执行数据库更新。
- 验收：省略字段保留、显式None、嵌套替换／合并、unknown、跨字段失败不改base、默认工厂不重复覆盖；schema.py及新增补丁入口，test_schema.py／test_deserialization.py。不冒称等价任意JSON Patch标准。

## 13．字段的多个输入别名（增强）

- 来源：外部API迁移旧字段名。data_key目前是单个名字，可在pre_load手工改键，但冲突／弃用提示需应用各自维护。
- 交付：输入别名列表与单一规范输出名；多别名同时出现明确冲突政策，可独立发弃用提示；字段属性名与外部名不混淆。
- 验收：旧／新名、两者同时有值、None、嵌套、unknown、partial、dump只用规范名；fields.py／schema.py，test_schema.py／test_deserialization.py。第04步冲突修复即使没有此增强也应成立。

## 14．未知字段收集到独立命名空间（增强）

- 来源：需要保留扩展数据又不让其与内部字段同层混合。已有INCLUDE直接追加，没有unknown收集字段选项。
- 交付：显式extras目标，载入时收集未知键，输出时按政策展开／保留；禁止与已知字段或目标名发生静默覆盖。
- 验收：空extras、已知名冲突、nested不同政策、错误类型、only/exclude、双向往返；schema.py，test_schema.py／test_serialization.py。原INCLUDE行为除第04步已明确的冲突外不改变。

## 15．带能力诊断的JSON Schema导出（增强）

- 来源：核心无to_json_schema，应用可用外部适配器／手工映射；字段metadata不是标准schema的等价替代。
- 交付：固定草案及支持子集，导出类型、必填、范围、嵌套与外部字段名；任意callable、钩子或无法翻译的规则必须诊断，不静默声称等价。
- 验收：独立标准validator对照正反数据、循环Schema引用、nullable、many、unsupported规则、别名；新增导出模块与测试，回归test_schema.py。归一化行为不能被当作纯验证规则导出。

## 16．可审查的Schema契约与一致性诊断（增强）

- 来源：Schema.fields与metadata已可读取，但没有稳定inspect_schema输出或多选项组合的诊断结果。
- 交付：只读描述字段内外名字、required/default/方向和钩子；报告同时load_only/dump_only、无效深路径、可判定矛盾范围等；默认不改变既有解析。
- 验收：继承、from_dict、自定义Field、递归、动态默认工厂不得被诊断器执行、descriptor输出确定；schema.py／fields.py，test_schema.py／test_options.py。此为原生工程审查工具，与第15步跨标准导出不同。

## 17．结构化错误码和精确路径贯穿聚合（增强）

- 来源：ValidationError已能存kwargs，直接Field可保留code；Schema聚合主要保留messages，实测业务REVIEW_CODE在总错误kwargs消失。
- 交付：稳定issue记录贯穿Field、And、Nested、many和schema校验，保留每叶code/参数/路径；旧messages接口可继续渲染。
- 验收：多个不同错误码、列表索引、字段含点、同一字段多个validator、自定义ValidationError、值脱敏；exceptions.py／error_store.py／validate.py，test_error_store.py／test_exceptions.py。不以一个全局kwargs覆盖所有叶子。

## 18．互相隔离的命名上下文通道（增强）

- 来源：experimental.Context已实现作用域恢复，但所有Generic别名共享一个_CURRENT_CONTEXT；不同库需要tenant与locale并行存在时需自行额外ContextVar。
- 交付：显式创建独立通道，分别get/set/default并正确恢复；保留现有单通道Context，不能只靠typing类型参数假装运行时隔离。
- 验收：两个通道嵌套、异常退出、并发asyncio任务、无值LookupError、线程传播政策；experimental/context.py，test_context.py。旧单通道嵌套恢复本轮已通过，不误称其损坏。

## 19．可选择的序列化方向验证（增强）

- 来源：dump当前不承诺执行load方向验证，自动数值转换是既有设计；需要严格对外数据契约的调用方须另做检查。
- 交付：独立validate_dump／显式序列化验证政策，明确验证原值还是输出值及可运行钩子；禁止直接load(dump(obj))导致有副作用的load处理器重复运行。
- 验收：非法输出类型、None/default、many聚合、输出别名、自定义Field、原dump不变；schema.py／fields.py，test_serialization.py／test_validate.py。按增强处理，不把默认dump行为全称bug。

## 20．按上下文决定字段是否参与处理（增强）

- 来源：[官方 #1953](https://github.com/marshmallow-code/marshmallow/issues/1953)。only/exclude是已存在的Schema选择，字段本身没有include_if动态政策，可由应用每次新建Schema替代。
- 交付：opt-in条件在明确阶段读取显式上下文，输出省略时不再求值该字段；载入收到禁用字段时拒绝／忽略由声明政策决定。
- 验收：同Schema不同上下文、默认值不复活被禁字段、谓词异常、nested/many、load_only/dump_only、并发隔离；fields.py／schema.py，test_fields.py／test_context.py。不得原地改共享declared_fields造成跨请求串扰。

## 冻结验收边界

上述改进尚未实施。本轮只执行原版全套与差异观察；后续须实际加载候选marshmallow，断言类型、错误结构、输入不变及文件输出，逐步累计原生回归。JSON Schema导出等互操作提案尚未写出，不能称已通过独立验收或已接入平台。
