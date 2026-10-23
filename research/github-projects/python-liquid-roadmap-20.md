# Python Liquid：二十步真实工程迭代路线

固定 [jg-rp/liquid@878f589adff6cb6bf08ccea7895570f96980248e](https://github.com/jg-rp/liquid/tree/878f589adff6cb6bf08ccea7895570f96980248e)，原生证据见 [单仓审查](./python-liquid.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．命名空间异步缓存与同步一致

- **来源／场景**：同一资料工作区用同步及异步接口加载note模板；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/builtin/loaders/mixins.py)。
- **原版缺口**：load_async把name传给缓存键位置，却把cache_key传给源加载；实测同步note正常，异步尝试docs/note后TemplateNotFoundError
- **交付及模块**：修正缓存键和真实模板名的参数位置，保证同步/异步共用相同缓存键合同；`liquid/builtin/loaders/mixins.py:CachingLoaderMixin`。
- **兼容与实际依赖**：保留namespace_key优先取kwargs再取context的既有规则；无命名空间行为不变；步骤依赖：无。
- **正常验收**：同一个workspace下同步和异步都加载原note，重复加载命中正确缓存
- **异常／边界验收**：两个workspace、context指定namespace、缓存过期、源不存在及不同globals都按相同规则处理
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 02．字典模板版本与显式失效

- **来源／场景**：本地编辑器修改DictLoader.templates后希望更新预览；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/builtin/loaders/dict_loader.py)。
- **原版缺口**：CachingDictLoader即使auto_reload=True也因uptodate=None保留旧解析；实测字典第二版仍渲染第一版，这是当前loader合同的能力缺口
- **交付及模块**：增加版本化字典loader或更新/失效API，使更新能原子替换解析结果；`liquid/builtin/loaders/dict_loader.py`, `liquid/builtin/loaders/mixins.py`。
- **兼容与实际依赖**：保留普通dict可变且不追踪的旧模式；不把现有手动清cache当不存在；新合同明确并发读取快照；步骤依赖：无。
- **正常验收**：通过受支持update变更模板后首次加载新内容，未变模板仍可命中
- **异常／边界验收**：删除、同内容更新、多个namespace和异步正在加载时不会返回混合版本
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 03．显式的跨模板依赖图

- **来源／场景**：资料构建器要知道修改row影响哪些报告；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/static_analysis.py)。
- **原版缺口**：analyze已有include_partials并合并变量/标签/过滤器，但TemplateAnalysis不返依赖边和动态引用状态
- **交付及模块**：新增dependency_graph，记录include/render/extends等边、来源span、动态目标及循环见证；`liquid/static_analysis.py`, `liquid/ast.py:PartialScope`, `liquid/extra/tags/extends_tag.py`。
- **兼容与实际依赖**：复用已有partial遍历，不重复宣称新支持静态分析；动态模板名不能假装静态确定；步骤依赖：无。
- **正常验收**：report到row形成明确边，反向查询列出受影响根模板
- **异常／边界验收**：循环、缺模板、参数影响作用域、重复partial和动态表达式都保留可解释未解析状态
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 04．渲染数据合同预检

- **来源／场景**：业务一次提交多层JSON，希望渲染前列出全部缺字段/类型问题；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/static_analysis.py)。
- **原版缺口**：global_variable_paths及StrictUndefined已有，但没有调用方schema加聚合预检，严格模式通常运行到首个缺值停止
- **交付及模块**：新增ContextSchema与validate_context，结合现有路径及显式类型声明输出诊断；`liquid/static_analysis.py`, `liquid/undefined.py`, `liquid/template.py`。
- **兼容与实际依赖**：不擅自推断所有过滤器的类型；默认宽容Undefined保持；动态路径只能标未知；步骤依赖：无。
- **正常验收**：输入用户/项目结构能一次报告两个缺字段，合法数据无误报
- **异常／边界验收**：条件分支可选字段、动态索引、列表元素、None和额外字段策略清楚，不运行自定义过滤器做预检
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 05．带元数据的过滤器注册

- **来源／场景**：团队过滤器要给工具提供参数说明与类型约束；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/environment.py)。
- **原版缺口**：add_filter接受任意callable，装饰器只标with_context/environment与转换行为，无统一参数/返回/纯度描述
- **交付及模块**：增加可选FilterSpec注册表，统一参数、异步、类型、说明和可选纯度标注；`liquid/environment.py:add_filter`, `liquid/filter.py`, `liquid/builtin/expressions/filtered.py`。
- **兼容与实际依赖**：原callable注册继续支持且默认metadata未知；不把用户自报pure当可自动证明；步骤依赖：无。
- **正常验收**：带spec的过滤器可静态检查参数个数并生成可读帮助，执行结果不变
- **异常／边界验收**：可变参数、装饰器、上下文注入、异步callable及未知spec版本不会错误拒绝旧插件
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 06．按词法作用域提供编辑补全

- **来源／场景**：模板编辑器在for体和render参数中需要不同变量建议；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/static_analysis.py)。
- **原版缺口**：静态分析给全模板变量及span，没有光标位置的可见作用域/过滤器参数建议合同
- **交付及模块**：新增complete_at，按AST作用域返回局部、全局、属性和过滤器建议及替换范围；`liquid/static_analysis.py`, `liquid/parser.py`, `liquid/token.py`。
- **兼容与实际依赖**：不把全局变量列表当完全缺编辑信息；未知业务对象不执行属性getter，仅用显式schema或安全描述；步骤依赖：无。
- **正常验收**：for体含item/forloop，体外不泄漏循环局部，过滤器处给已注册候选
- **异常／边界验收**：未闭合标签、中文位置、raw/comment、动态索引和自定义tag未知作用域给保守结果
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 07．保持作用域的变量重命名

- **来源／场景**：维护者重命名某一局部assign或for变量；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/static_analysis.py)。
- **原版缺口**：原版可列引用位置，但没有绑定关系与编辑计划，简单文本替换会改变注释/字符串或同名其他局部
- **交付及模块**：新增rename_variable编辑计划，区分声明与绑定引用并预检冲突；`liquid/static_analysis.py`, `liquid/builtin/expressions/path.py`, `liquid/ast.py`。
- **兼容与实际依赖**：默认只出补丁不写文件；外部schema字段与局部变量重命名分开，不修改动态字符串键；步骤依赖：无。
- **正常验收**：重命名for局部item只改变对应绑定及引用，渲染输出保持
- **异常／边界验收**：局部遮蔽、capture/assign、render独立作用域、冲突名及不完整源码明确拒绝或保留未知
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 08．保留模板语义的源码格式化

- **来源／场景**：报告模板需要统一缩进和标签间距；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/lex.py)。
- **原版缺口**：lexer/parser把源码转令牌/AST，raw与空白裁剪信息会处理掉；无源码formatter
- **交付及模块**：增加保留原始片段的格式化层，统一标签内部排版与结构缩进，给出文本补丁；`liquid/lex.py`, `liquid/parser.py`, `liquid/token.py`。
- **兼容与实际依赖**：不随意改正文空白、trim连字符、raw或注释；默认不以重排AST重建任意原文；步骤依赖：无。
- **正常验收**：格式化嵌套for/if后再次格式化幂等，样例渲染字节相同
- **异常／边界验收**：自定义分隔符、liquid多语句、inline标签、未闭合源码和自定义tag采用安全回退
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 09．编辑会话的增量解析

- **来源／场景**：长模板每次编辑一个字段需实时语法与变量反馈；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/environment.py)。
- **原版缺口**：from_string每次完整词法分析并创建节点；parser缓存的是解析器对象，并非增量源码结果
- **交付及模块**：新增edit_session，追踪版本/文本编辑并复用未受影响区域，失败时可完整重解析；`liquid/environment.py:from_string`, `liquid/lex.py`, `liquid/parser.py`。
- **兼容与实际依赖**：保持完整解析作为正确性参照；可回退而不承诺任意改动恒定时间；不复用跨环境不兼容节点；步骤依赖：无。
- **正常验收**：局部文字及表达式修改后的AST/诊断与重新from_string一致
- **异常／边界验收**：跨块边界编辑、raw终止、trim、分隔符配置变更和过期编辑版本正确失效
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 10．独立环境派生与配置快照

- **来源／场景**：同一应用需要两个报告配置，各自覆盖过滤器而共享已知基础设置；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/environment.py)。
- **原版缺口**：Environment属性、tags/filters/globals可变，没有overlay或稳定配置描述；手工复制容易漏掉额外语言开关
- **交付及模块**：新增明确overlay/freeze配置快照，控制loader共享与注册表复制，给配置版本指纹；`liquid/environment.py`, `liquid/extra/__init__.py`。
- **兼容与实际依赖**：保留直接创建与可变注册；冻结仅影响新选择的对象，不冻结业务输入，不把callable地址当跨进程稳定身份；步骤依赖：无。
- **正常验收**：派生环境覆盖一个过滤器不影响父环境，完整语言选项与默认行为可核对
- **异常／边界验收**：自定义tag实例、可变globals、共享loader、冻结后注册和未标识插件均有明确策略
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 11．可移交的模板源码包

- **来源／场景**：离线报告交付需要根模板及依赖子模板一起固定；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/loader.py)。
- **原版缺口**：FileSystem/Package/DictLoader能装载，但没有带清单、根入口、依赖闭包与配置说明的发布包合同
- **交付及模块**：新增template bundle，打包原始源码、内容摘要、入口与显式插件/环境需求；`liquid/loader.py`, `liquid/builtin/loaders/dict_loader.py`, `liquid/static_analysis.py`。
- **兼容与实际依赖**：包存原始源码和元数据，不序列化任意Python对象；动态依赖需调用方清单补齐，不假称自动完整；步骤依赖：无。
- **正常验收**：带report/row的包在新的DictLoader环境离线渲染相同结果，摘要可核验
- **异常／边界验收**：缺依赖、重名模板、版本不兼容、动态目标和自定义插件缺失应在加载包时解释
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 12．跨进程的编译缓存接口

- **来源／场景**：反复启动的本地报告任务每次重做同一解析；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/builtin/loaders/mixins.py)。
- **原版缺口**：已有LRU缓存保存BoundTemplate且支持auto_reload，但只在内存，没有版本化持久编译缓存合同
- **交付及模块**：新增可选持久编译缓存，缓存可验证的内建节点表示并以源码/环境/插件版本联合寻址；`liquid/builtin/loaders/mixins.py`, `liquid/parser.py`, `liquid/template.py`。
- **兼容与实际依赖**：不把普通pickle当通用缓存格式；自定义节点无适配时回退源码编译；缓存不是源码bundle；步骤依赖：无。
- **正常验收**：第二个进程读取兼容缓存时渲染与冷编译相同，变源/配置信息正确miss
- **异常／边界验收**：旧版本、损坏缓存、未知节点、并发写入和插件身份不确定时安全回退而非误渲染
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 13．输出位置到模板来源映射

- **来源／场景**：校对者点击周报中的一段文字想回到子模板表达式；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/template.py)。
- **原版缺口**：Token有start_index，静态分析有span；render只返文字或写buffer，没有运行输出到模板/节点/输入路径关系
- **交付及模块**：新增opt-in render_with_source_map，记录输出区间与模板span、循环迭代和capture来源；`liquid/template.py`, `liquid/ast.py`, `liquid/token.py`, `liquid/context.py`。
- **兼容与实际依赖**：默认不保存业务值；映射不是逐字符一一对应，过滤器转换可多对多；原render返回值保持；步骤依赖：无。
- **正常验收**：report中row每次迭代的输出能定位row模板对应表达式，中文字节/字符坐标区分
- **异常／边界验收**：capture后再过滤、零输出、转义扩展、include作用域及自定义节点无来源明确标注
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 14．一次渲染的执行剖析

- **来源／场景**：维护者要定位哪个子模板或过滤器占用时间；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/ast.py)。
- **原版缺口**：源码有AST/分析与外部performance脚本，缺稳定的逐次渲染事件/调用统计接口
- **交付及模块**：新增RenderObserver，记录节点、过滤器、partial的进入/退出、耗时和调用次数；`liquid/ast.py:Node`, `liquid/context.py:filter`, `liquid/template.py`。
- **兼容与实际依赖**：默认关闭且不记录参数值；不把外部性能脚本说成不存在；同步/异步属于同一观察合同；步骤依赖：无。
- **正常验收**：多个row调用与自定义慢过滤器在统计中准确出现，最终输出保持
- **异常／边界验收**：异常退出、递归、取消、回调错误及异步嵌套的时间归属和完成状态明确
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 15．拉取式分段渲染输出

- **来源／场景**：本地大报告希望逐段消费而不是取得完整字符串；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/template.py)。
- **原版缺口**：已有render_with_context可写任意TextIO，render/async用StringIO；没有供消费者pull的iter_render合同
- **交付及模块**：增加同步/异步输出迭代器，界定分段、背压和消费者关闭时的上下文清理；`liquid/template.py`, `liquid/ast.py`, `liquid/output.py`。
- **兼容与实际依赖**：保留已有推送buffer API；capture、sort等仍可能内部缓冲，不能宣称所有模板恒定内存；步骤依赖：无。
- **正常验收**：逐段拼接等于render，消费者暂停时不继续产生后续节点输出
- **异常／边界验收**：空模板、单节点大输出、capture、break/continue、异常和提前close不遗留上下文
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 16．带记录标识的批量渲染

- **来源／场景**：同一报告模板应用于一批业务JSON，希望隔离失败记录；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/template.py)。
- **原版缺口**：现有入口一次渲染一个context；无有序记录结果、聚合诊断及受限异步调度合同
- **交付及模块**：增加render_records，保留id/顺序并提供continue/fail-fast与可选有界并发；`liquid/template.py`, `liquid/environment.py`, `liquid/context.py`。
- **兼容与实际依赖**：每条使用独立RenderContext，模板可共享但不共享assign/cycle状态；同步/异步一次交付；步骤依赖：无。
- **正常验收**：三条记录一条缺值时按策略报告，其余输出与独立render相同
- **异常／边界验收**：重复id、生成器中断、单条异常、消费者提前结束和异步取消有准确已完成/未执行状态
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 17．可复现的渲染时钟

- **来源／场景**：定时报表重跑历史月份时now/today需一致；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/context.py)。
- **原版缺口**：Builtin动态对象和date过滤器分别调用datetime.now/date.today；可传显式日期但不能统一接管内置字符串now
- **交付及模块**：新增Clock配置和每次渲染时间快照，统一内置对象及普通/额外日期过滤器；`liquid/context.py:BuiltIn`, `liquid/builtin/filters/misc.py:date`, `liquid/extra/filters/babel.py`。
- **兼容与实际依赖**：默认仍为系统时间；用户传显式date/datetime不覆盖；时区必须明确，不默改naive日期语义；步骤依赖：无。
- **正常验收**：固定时钟时所有now/today在一次报告中一致，重跑完全可复现
- **异常／边界验收**：跨午夜、时区切换、夏令时和并发不同快照不串用，全局系统时间不被修改
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 18．翻译目录与模板占位符核验

- **来源／场景**：多语报告新增变量后要检查译文目录是否匹配；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/messages.py)。
- **原版缺口**：已有gettext/pgettext/复数过滤器、翻译tag和Babel消息提取，缺将目录与模板使用合同一起核验的入口
- **交付及模块**：新增audit_catalog，检查缺译项、上下文/复数项与格式化占位符，关联源码span；`liquid/messages.py`, `liquid/extra/filters/translate.py`, `liquid/extra/tags/translate_tag.py`。
- **兼容与实际依赖**：不重计现有翻译或消息提取；不自动改写译文，普通缺译回退行为保持；步骤依赖：无。
- **正常验收**：源消息与中文目录占位符一致时通过，漏变量或错误context定位到模板
- **异常／边界验收**：动态消息、复数语言规则、转义花括号、unused目录项及自定义TranslatableFilter给明确诊断
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 19．空白裁剪的可解释预览

- **来源／场景**：邮件排版中两段文字因trim连字符或空白块省略粘连；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/liquid/lex.py)。
- **原版缺口**：lex使用lstrip/rstrip，节点有blank与suppress_blank_control_flow_blocks；当前最终输出不说明空白为何消失
- **交付及模块**：新增whitespace audit，展示源空白保留/裁剪范围、触发规则及输出定位；`liquid/lex.py`, `liquid/ast.py`, `liquid/environment.py`。
- **兼容与实际依赖**：只解释已有裁剪语义不默认改变它；与source map共同定位，避免新增一套不一致的渲染器；步骤依赖：13。
- **正常验收**：A换行及双侧trim表达式能看到为何得到A中文B，禁用省略的差异明确
- **异常／边界验收**：Unicode空白、CRLF、raw、空capture及部分模板中的边界裁剪准确归属
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。

## 20．本地模板项目命令入口

- **来源／场景**：资料团队用固定模板和JSON资料生成周报并查看分析；[固定源码](https://github.com/jg-rp/liquid/blob/878f589adff6cb6bf08ccea7895570f96980248e/pyproject.toml)。
- **原版缺口**：pyproject未声明业务console entry；现有scripts是性能/维护工具，无项目render/inspect合同
- **交付及模块**：新增本地CLI，显式模板根、入口、JSON数据和输出文件，支持现有分析的机器结果；`pyproject.toml`, `liquid/environment.py`, `liquid/static_analysis.py`。
- **兼容与实际依赖**：默认不猜数据格式、不覆盖来源模板；使用既有loader与渲染逻辑，不自行实现Liquid语言；步骤依赖：无。
- **正常验收**：给模板目录与JSON生成周报，inspect返回变量/过滤器/标签和清楚退出码
- **异常／边界验收**：缺模板、坏JSON、未知过滤器、空输出、输出路径冲突和写盘中断能定位且不留半成品
- **原生回归**：`tests/test_template_api.py`, `tests/test_dict_loader.py`, `tests/test_static_analysis.py`, `tests/test_analyze_template_tags.py`, `tests/test_registered_filters.py`, `tests/test_undefined.py`, `tests/test_extract_translation_messages.py`, `tests/test_compliance.py`。
