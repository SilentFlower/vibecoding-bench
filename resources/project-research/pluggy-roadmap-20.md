# Pluggy：二十步真实工程迭代路线

固定 [pytest-dev/pluggy@0224f79fc75efadaafe24dbab9deee2ff616ecd7](https://github.com/pytest-dev/pluggy/tree/0224f79fc75efadaafe24dbab9deee2ff616ecd7)，原生证据见 [单仓审查](./pluggy.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．历史调用保存参数映射快照

- **类型与来源**：修复；[官方#808](https://github.com/pytest-dev/pluggy/issues/808) 与固定源码/原版观察。
- **原版现状与收益**：call_historic后调用者把value改为mutated，延后注册插件收到mutated而非at-call-time。
- **交付及模块**：应用spec默认值后浅复制kwargs映射再记历史，调用与重放语义一致；_caller.HookCaller.call_historic／_apply_defaults。
- **兼容与依赖**：只复制映射，不深复制用户mutable参数值；有无spec defaults不能改变隔离行为；步骤依赖：无。
- **正常验收**：延后插件收到调用时的at-call-time，原映射改动不影响历史。
- **异常／边界验收**：空mapping、自定义Mapping、默认值、嵌套mutable值共享按明示浅复制契约。
- **原生回归**：testing/test_hookcaller.py、testing/test_pluginmanager.py。

## 02．拒绝注册的入口点不污染distribution清单

- **类型与来源**：修复；[官方#807](https://github.com/pytest-dev/pluggy/issues/807) 与固定源码/原版观察。
- **原版现状与收益**：ep.load返回None时register拒绝，但count仍1且_name2dist记名，list_plugin_distributions抛KeyError。
- **交付及模块**：仅register实际返回名字时计数和记录分发映射，使用返回的名字；_manager.PluginManager.load_setuptools_entrypoints／list_plugin_distributions。
- **兼容与依赖**：阻止名、已注册名和子类register重新命名行为保持，不能用已存在插件冒充新加载；步骤依赖：无。
- **正常验收**：None或子类主动拒绝入口计数0、分发清单可读，成功入口真实关联。
- **异常／边界验收**：register返回不同名、load异常、多个dist同名、后续unregister清除关联。
- **原生回归**：testing/test_pluginmanager.py。

## 03．带默认的位置专用参数按位置交付

- **类型与来源**：修复；[官方#774](https://github.com/pytest-dev/pluggy/issues/774) 与固定源码/原版观察。
- **原版现状与收益**：hookimpl render(value=fallback,/)在value=caller时TypeError，默认参数被kwargnames路径按keyword传递。
- **交付及模块**：记录真实Parameter.kind，按位置补齐前序默认值，再传其余合法keyword；_decorators.varnames、_impl.HookImpl、_execution._multicall／run_old_style_hookwrapper。
- **兼容与依赖**：保留当前spec默认值与显式值优先；不可通过删默认值丢失用户契约；步骤依赖：无。
- **正常验收**：普通/旧wrapper/新wrapper的posonly默认参数收到caller。
- **异常／边界验收**：只提供后一个optional posonly、必填缺失、mixed参数、firstresult与异常展开。
- **原生回归**：testing/test_multicall.py、testing/test_details.py。

## 04．注销参数校验不依赖优化开关

- **类型与来源**：修复；[官方#762](https://github.com/pytest-dev/pluggy/issues/762) 与固定源码/原版观察。
- **原版现状与收益**：python -O下unregister()返回None、unregister未注册对象原样返回，正常模式依赖assert。
- **交付及模块**：在公开边界显式校验省略参数和未注册对象，异常契约与-O一致；_manager.PluginManager.unregister。
- **兼容与依赖**：说明AssertionError迁移为TypeError/ValueError的兼容变化；按name未知返回None仍保留；步骤依赖：无。
- **正常验收**：合法按plugin/name注销后全部hooks消失，优化模式与普通一致。
- **异常／边界验收**：双参数不一致、blocked名、未注册对象、None和重复注销无误删。
- **原生回归**：testing/test_pluginmanager.py。

## 05．插件注册与移除按对象身份判断

- **类型与来源**：修复；[官方#760](https://github.com/pytest-dev/pluggy/issues/760) 与固定源码/原版观察。
- **原版现状与收益**：dataclass两个不同实例eq=True，第二个注册被拒；get_name(second)误返回one；_remove_plugin也用!=。
- **交付及模块**：注册/查询/注销实现统一用is识别插件对象，避免用户__eq__控制registry；_manager.register／get_name／is_registered、_caller._remove_plugin。
- **兼容与依赖**：同一对象重复注册仍拒；既有get_plugins返回set的hashability边界须保持或另明确迁移，不额外承诺不可hash对象在该API可用；步骤依赖：无。
- **正常验收**：两相等实例用不同名可注册，移除一个不移另一个，查询未注册相等对象为None。
- **异常／边界验收**：__eq__抛异常/返回数组、相等于None、共享同一实例别名与hook子集。
- **原生回归**：testing/test_pluginmanager.py、testing/test_hookcaller.py。

## 06．协议安装与历史重放失败保持注册表一致

- **类型与来源**：修复；[官方#761](https://github.com/pytest-dev/pluggy/issues/761) 与固定源码/原版观察。
- **原版现状与收益**：add_hookspecs先安装spec再验证，失败后重试已注册；historic replay抛错仍has_plugin(broken)=True。
- **交付及模块**：校验/准备阶段与提交分开，失败移除本轮新spec/hookimpl/registry映射且保留先前状态；_manager.add_hookspecs／register、_caller.set_specification／_maybe_apply_history。
- **兼容与依赖**：不能撤销插件已执行的任意外部副作用；只保证管理器拥有状态回滚，现有成功注册顺序保持；步骤依赖：01、05。
- **正常验收**：坏spec或坏replay失败后修正重试可成功，原插件正常调用。
- **异常／边界验收**：多个spec部分成功、重放中递归注册、已有hook无spec、用户回调异常与分发映射。
- **原生回归**：testing/test_pluginmanager.py、testing/test_hookcaller.py。

## 07．关键字专用hook参数的明确支持

- **类型与来源**：增强；[官方#742](https://github.com/pytest-dev/pluggy/issues/742) 与固定源码/原版观察。
- **原版现状与收益**：varnames明确排除keyword-only，声明这类参数会被忽略，无法稳定传入所需值。
- **交付及模块**：将required/default keyword-only纳入spec/impl验证和调用，保持只按合法kind传参；_decorators.varnames、HookSpec／HookImpl、_execution._multicall。
- **兼容与依赖**：现有普通hook热路径保留；参数名裁剪仍允许impl仅接子集，未知调用字段策略不偷换；步骤依赖：03。
- **正常验收**：hook(value,*,mode)与可选mode都正常接收显式/默认值。
- **异常／边界验收**：缺required key、wrapper、posonly混用、**kwargs不自动吞所有协议外值。
- **原生回归**：testing/test_details.py、testing/test_multicall.py。

## 08．可选的协议输入输出类型检查

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：现有验证检查参数名和wrapper结构，不验证hookspec标注的运行值类型。
- **交付及模块**：在显式validation profile下检查常见builtins/Union/Optional/container参数与返回值，错误带plugin/hook路径；HookSpec元信息、_manager验证profile、_execution调用边界。
- **兼容与依赖**：默认无运行类型检查；不eval不可信字符串注解或导入任意模块，未知注解明示未支持；步骤依赖：07。
- **正常验收**：int协议收到int并返回int通过，插件错误str结果定位具体plugin。
- **异常／边界验收**：ForwardRef/Any、嵌套容器成本上限、firstresult/None、wrapper改结果后的检查位置。
- **原生回归**：testing/test_details.py、testing/test_multicall.py。

## 09．异步hook及混合wrapper调用协议

- **类型与来源**：增强；[官方#378](https://github.com/pytest-dev/pluggy/issues/378) 与固定源码/原版观察。
- **原版现状与收益**：HookCaller只有同步调用，async函数结果会作为coroutine值返回，没有await链和async wrapper展开。
- **交付及模块**：新增显式call_async，协同等待async impl并定义同步impl桥接及取消展开；_caller.HookCaller、_execution新async调用器、Hookimpl标记验证。
- **兼容与依赖**：同步__call__不偷偷run event loop；旧同步wrapper支持边界明确，不把并行调度拆成额外步骤；步骤依赖：无。
- **正常验收**：async实现await后输出与顺序一致，混合同步插件按约定执行。
- **异常／边界验收**：取消/超时、async wrapper少/多yield、异常链、firstresult与禁止historic组合。
- **原生回归**：testing/test_multicall.py、新增原生async调用回归。

## 10．调用结果保留产生它的插件信息

- **类型与来源**：增强；[官方#235](https://github.com/pytest-dev/pluggy/issues/235) 与固定源码/原版观察。
- **原版现状与收益**：普通hook返回匿名非None值列表，调用者不能稳定对应plugin，monitoring只包围总调用。
- **交付及模块**：新增显式call_with_provenance返回plugin_name/hookimpl/value记录，并说明wrapper改写结果归属；_execution结果收集、_caller.HookCaller新入口。
- **兼容与依赖**：默认列表/firstresult结果不变；不靠结果相等反查插件，不把wrapper生成的聚合值伪造为某个impl；步骤依赖：无。
- **正常验收**：两个插件返回同值仍有不同来源，顺序与实际调用顺序一致。
- **异常／边界验收**：None过滤、firstresult、wrapper聚合新结果、已注销插件和异常来源。
- **原生回归**：testing/test_multicall.py、testing/test_invocations.py。

## 11．可提前停止的逐插件结果迭代

- **类型与来源**：增强；[官方#50](https://github.com/pytest-dev/pluggy/issues/50) 与固定源码/原版观察。
- **原版现状与收益**：现有全量调用先执行所有插件，firstresult只能首非None；无法按消费方检查决定继续。
- **交付及模块**：新增iter_results协议，按需调用下个impl，close时保证已启动wrapper正确退出；_caller新iterator入口、_execution可关闭迭代器。
- **兼容与依赖**：默认__call__保持全量；明确首版允许的wrapper组合，提前停止不启动后续插件，不能仅先执行全量再yield；步骤依赖：无。
- **正常验收**：先取缓存插件结果并接受后，不触发需要交互的后备插件。
- **异常／边界验收**：提前close、消费异常、impl异常、零结果、wrapper清理与firstresult冲突拒绝。
- **原生回归**：testing/test_multicall.py、testing/test_invocations.py。

## 12．作用域内临时注册插件集合

- **类型与来源**：增强；[官方#52](https://github.com/pytest-dev/pluggy/issues/52) 与固定源码/原版观察。
- **原版现状与收益**：register/unregister已有，但无原生context manager为一次操作注册并恢复集合。
- **交付及模块**：新增registered(...)上下文，只追踪本轮真正新增的插件，异常退出按身份移除；_manager.PluginManager新context helper。
- **兼容与依赖**：已有插件/blocked状态不被清除；不重置整个管理器，不覆盖同名陌生插件；步骤依赖：05、06。
- **正常验收**：with内新增hook有效，退出后只剩原插件，嵌套上下文独立。
- **异常／边界验收**：中途注册失败、相同实例重复、作用域内主动注销/重新注册与历史重放失败。
- **原生回归**：testing/test_pluginmanager.py。

## 13．显式插件相对顺序与约束诊断

- **类型与来源**：增强；[官方#705](https://github.com/pytest-dev/pluggy/issues/705) 与固定源码/原版观察。
- **原版现状与收益**：tryfirst/trylast只能分优先组，before/after指定另一个插件的需求未支持。
- **交付及模块**：可选声明排序约束，用稳定拓扑排序形成每hook调用顺序并报告缺目标/环；HookimplOpts、_caller._add_hookimpl、_manager约束校验。
- **兼容与依赖**：默认注册顺序/优先组保持；明确约束和tryfirst/trylast冲突策略，上游倾向wontfix仅作试点提案；步骤依赖：06。
- **正常验收**：A before B、C after B形成稳定顺序，无声明插件仍保留相对顺序。
- **异常／边界验收**：循环、未知/注销目标、同plugin多个specname、wrapper与普通层级不能互穿。
- **原生回归**：testing/test_hookcaller.py、testing/test_invocations.py。

## 14．逐实现的结构化调用追踪

- **类型与来源**：增强；[官方#588](https://github.com/pytest-dev/pluggy/issues/588) 与固定源码/原版观察。
- **原版现状与收益**：add_hookcall_monitoring已有总调用before/after，但无每impl及wrapper阶段的稳定事件协议。
- **交付及模块**：增加可选结构化trace subscriber，含call_id/parent/hook/plugin/phase/outcome/timing；_execution每impl边界、_tracing、_manager监控管理。
- **兼容与依赖**：不重复新增已有总监控；默认禁用成本接近零，不允许trace回调篡改业务结果，敏感kwargs策略显式；步骤依赖：无。
- **正常验收**：一次嵌套hook能重建各插件进入/退出和wrapper栈，不混淆父子调用。
- **异常／边界验收**：impl异常、trace回调失败、递归/并发、firstresult未执行插件不伪造span。
- **原生回归**：testing/test_tracer.py、testing/test_multicall.py。

## 15．管理插件资源的启动与关闭生命周期

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：注册只发现hook，不调用资源启动/关闭；应用插件持有文件/连接时需自行编排。
- **交付及模块**：新增显式managed lifecycle context，插件提供约定setup/teardown并在失败时反序清理已启动项；_manager新增生命周期协议、registry资源状态。
- **兼容与依赖**：普通register不自动执行新方法；不把退出context等同unregister，资源和注册归属规则明确；步骤依赖：06。
- **正常验收**：两个合成资源按顺序setup、退出反序teardown，各只一次。
- **异常／边界验收**：setup中途失败、teardown多错聚合、重复进入、register失败后未启动对象。
- **原生回归**：testing/test_pluginmanager.py、新增原生lifecycle回归。

## 16．加载前查看并筛选入口点元数据

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：load_setuptools_entrypoints直接ep.load后注册，分发清单仅展示已加载对象，缺无import预览。
- **交付及模块**：新增discover_entrypoints返回group/name/value/distribution/version候选，可显式选择后按冻结候选加载；_manager入口点发现、_compat分发元数据表示。
- **兼容与依赖**：默认load接口保留；metadata不可用单独报告，预览不执行ep.load，不称它能证明插件行为安全；步骤依赖：02。
- **正常验收**：预览含合成入口但load计数仍0，选择某一项后仅该项实际导入并注册。
- **异常／边界验收**：重复名、坏metadata、预览后环境变动、被blocked项和拒绝注册。
- **原生回归**：testing/test_pluginmanager.py。

## 17．历史hook的容量与清理策略

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：_call_history列表无上限且长期持有kwargs引用；不能清空/按窗口保留原生历史。
- **交付及模块**：新增显式history retention配置与clear_history，按条数/选择器裁剪已记录事件；_caller.HookCaller._call_history／call_historic。
- **兼容与依赖**：默认无限历史保持；裁剪影响未来重放须显式，正在重放使用稳定快照；步骤依赖：01。
- **正常验收**：上限3时只给新插件重放最后3条，clear后不重放旧值。
- **异常／边界验收**：上限0/负值、replay期间追加/clear、result_callback与mutable参数浅复制规则。
- **原生回归**：testing/test_hookcaller.py、testing/test_pluginmanager.py。

## 18．hook协议改名的兼容迁移适配

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：impl的specname能改Python方法名映射，却不能让旧hookspec调用别名自动迁移新协议/参数。
- **交付及模块**：新增显式alias adapter，将旧hook名和参数映射到新hook并给定弃用诊断；_manager协议别名表、HookCaller代理、spec元信息。
- **兼容与依赖**：不重复已有specname/warn_on_impl；默认无alias，不能让别名重复调用同一个插件，循环声明拒绝；步骤依赖：07。
- **正常验收**：旧name/old_arg调用经adapter得到新name/new_arg结果，直接新调用结果一致。
- **异常／边界验收**：缺字段、old/new同名冲突、别名环、firstresult差异及wrapper归属。
- **原生回归**：testing/test_details.py、testing/test_invocations.py。

## 19．逐插件隔离异常的受控调用模式

- **类型与来源**：增强；固定PluginManager/HookCaller/_multicall定义与原生插件使用场景。
- **原版现状与收益**：_multicall遇异常停止并交wrapper，普通调用无法收集多个独立插件的失败结果。
- **交付及模块**：新增显式call_collect_errors返回每plugin成功/异常记录，继续调用其他普通impl；_execution新调用策略、_caller入口、_result记录类型。
- **兼容与依赖**：默认传播异常保持；KeyboardInterrupt/SystemExit不当普通插件失败吞掉；wrapper与firstresult支持范围明确；步骤依赖：10。
- **正常验收**：一坏两好插件全部实际执行，返回三条可追溯结果。
- **异常／边界验收**：wrapper异常不能伪造某impl失败、异常持有traceback生命周期、无插件和嵌套hook。
- **原生回归**：testing/test_multicall.py、testing/test_result.py。

## 20．由hookspec生成可检查的调用端类型接口

- **类型与来源**：增强；[官方#191](https://github.com/pytest-dev/pluggy/issues/191) 与固定源码/原版观察。
- **原版现状与收益**：标记器本身已保留函数泛型，HookRelay仍为动态HookCaller；用户需手工cast协议，缺稳定typed client/stub输出。
- **交付及模块**：提供显式build-time stub/protocol生成器，输出已声明hook关键字参数和实际返回形态；HookSpec元数据、HookRelay类型导出helper、独立生成入口。
- **兼容与依赖**：不重复已完成的marker注解；不eval注解，不运行plugin；multicall返回list与firstresult返回optional必须区分；步骤依赖：07。
- **正常验收**：生成interface可让mypy/pyright捕获错误参数名/类型，合法调用通过。
- **异常／边界验收**：未解析ForwardRef、自定义类型import路径、keyword-only/posonly、无标注hook及重名覆盖。
- **原生回归**：testing/test_details.py、新增生成接口的静态检查夹具。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
