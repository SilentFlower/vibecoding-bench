# DeepDiff：二十步真实工程迭代路线

固定 [qlustered/deepdiff@79e4379278b1cfdd8e9e3dccac364956908e8989](https://github.com/qlustered/deepdiff/tree/79e4379278b1cfdd8e9e3dccac364956908e8989)，详见[单仓审查](./deepdiff.md)。共 20 步：16 项增强提案、4 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．复数负虚部精度格式化（问题修复）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/551
- 原版现状：number_to_string将real和负imag固定用+拼接成1+-1j，complex构造抛ValueError；当前提交已复现。
- 交付目标：正确构造复数/格式化符号，保持real与imag分别应用精度。
- 影响模块：deepdiff/helper.py:number_to_string；DeepHash/DeepDiff调用方
- 兼容边界：保留f/e notation和现有零归一化，不只为1-1j写特殊分支。
- 正常验收：正负实部/虚部组合可格式化，Diff/Hash带significant_digits不崩溃。
- 异常／边界：负0、纯虚数、0精度、极小指数、NaN/Infinity与complex子类规则。
- 原生回归：tests/test_helper.py；test_diff_math.py；test_hash.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．date 对象不套用时分秒截断（问题修复）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/564
- 原版现状：比较date且truncate_datetime=minute会调用date.replace(second=0)，当前TypeError复现。
- 交付目标：仅对支持的datetime/time做对应精度截断，date按日期正常比较。
- 影响模块：deepdiff/helper.py:datetime_normalize；diff.py:_diff_time
- 兼容边界：不把date强制转datetime或改变默认时区；datetime既有规则保持。
- 正常验收：同日date相等、异日有差异，second/minute/hour/day选项都不传非法字段。
- 异常／边界：混合date/datetime类型、dict/list/Hash、None截断和自定义日期子类。
- 原生回归：tests/test_diff_datetime.py；tests/test_hash.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．忽略类型配置下的日期时间字典键（问题修复）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/550
- 原版现状：datetime作为字典键且ignore_numeric_type_changes=True时进入number_to_string/round，抛TypeError；已复现。
- 交付目标：键归一化仅对真实数值应用数值规则，时间键保留独立规范化。
- 影响模块：deepdiff/diff.py:字典key清洗；deephash.py
- 兼容边界：不改变数值键按配置合并的语义，ignore_string_case仅处理字符串。
- 正常验收：同datetime键的10/10.0在忽略数值类型时正确相等，时间不同仍有差异。
- 异常／边界：date/time/Decimal混合键、大小写开关、bytes键、None与显式exclude/include。
- 原生回归：tests/test_diff_datetime.py；tests/test_diff_text.py；tests/test_hash.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．原生固定偏移时区对象比较（问题修复）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/466
- 原版现状：DeepDiff(timezone.utc,timezone(+1h))当前返回{}，Python原生相等判断为False。
- 交付目标：专门处理datetime.timezone固定偏移对象，按偏移表达差异。
- 影响模块：deepdiff/diff.py:类型分派；helper.py
- 兼容边界：首版限定datetime.timezone，不承诺任意动态tzinfo；同偏移不同展示名按Python相等规则兼容。
- 正常验收：UTC/+01/+02各有差异，同偏移对象相等，嵌套结构也可比较。
- 异常／边界：负/非整小时偏移、不同tzinfo类走原类型规则，序列和Hash一致。
- 原生回归：tests/test_diff_datetime.py；tests/test_hash.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．自定义操作器可选择遵守路径过滤（增强提案）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/633
- 原版现状：_use_custom_operator在_skip_this前调用，排除b仍记录operator调用；结果{}但是否应禁止回调是行为政策，非擅自认定BUG。
- 交付目标：增加operators_respect_exclusions选项，开启时已排除层级不调用自定义operator。
- 影响模块：deepdiff/diff.py:_diff/_use_custom_operator/_skip_this
- 兼容边界：默认兼容原顺序；仅前移不依赖operator结果的路径过滤，避免改变未排除节点。
- 正常验收：合成a/b对象排除b时operator只收到a，普通比较结果相同。
- 异常／边界：include/exclude/glob/regex组合、identity相同、operator报自定义结果与callback过滤的顺序清楚。
- 原生回归：tests/test_operators.py；test_glob_paths.py；test_diff_include_paths.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．毫秒级时间截断（增强提案）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/477
- 原版现状：get_truncate_datetime仅接受second/minute/hour/day，millisecond当前ValueError。
- 交付目标：允许millisecond，将microsecond向下截断到1000倍数，并同步Hash与CLI。
- 影响模块：deepdiff/helper.py:时间校验/归一化；commands.py
- 兼容边界：默认不变；明确truncate为截断非四舍五入，保留时区归一化。
- 正常验收：1001us与1002us在毫秒模式相等，1999/2000us不同。
- 异常／边界：日期对象沿第02步规则、跨秒、time对象、负Epoch瞬间与CLI参数一致。
- 原生回归：tests/test_diff_datetime.py；test_hash.py；test_command.py
- 真实依赖：02

## 07．可选报告相等叶子路径（增强提案）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/553
- 原版现状：只报告差异，没有include_matched_values；内部匹配集合不作为公共结果。
- 交付目标：新增可选matched_paths/values输出，明确仅实际验证的叶子且可限制数量。
- 影响模块：deepdiff/diff.py；model.py；serialization.py
- 兼容边界：默认无额外成本；exclude不是matched，达到上限必须标明截断。
- 正常验收：订单未改region列出matched，qty列出changed，不重复祖先所有节点。
- 异常／边界：identity快速相等整树、ignore_order配对、数值容差相等和巨大匹配集上限。
- 原生回归：tests/test_diff_tree.py；test_diff_text.py；test_serialization.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．比较双方的展示标签（增强提案）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/531
- 原版现状：text输出固定old_value/new_value、tree表示固定t1/t2，用户需后处理。
- 交付目标：to_report增加显式left_label/right_label映射，用于人读报告与JSON展示。
- 影响模块：deepdiff/serialization.py；model.py 的表示层
- 兼容边界：内部diff/Delta契约仍old/new，不将标签写回可执行Delta或改变patch字段。
- 正常验收：API结果与设备状态使用api/device标签，原值和路径不变。
- 异常／边界：标签重名/空白/保留键冲突拒绝，tree/text/JSON一致，原to_dict兼容。
- 原生回归：tests/test_serialization.py；test_diff_tree.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．声明策略的组合深合并（增强提案）

- 来源／场景：https://github.com/qlustered/deepdiff/issues/552
- 原版现状：Delta使base变成目标，不是同时保留双方键的组合合并；官方也提到第三方deepmerge替代。
- 交付目标：提供独立DeepMerge工具，显式dict递归、列表replace/append和冲突策略。
- 影响模块：新增deepdiff合并模块；helper/model可复用类型工具
- 兼容边界：不改Delta语义，不默认合并任意Python对象属性，首版JSON-like容器。
- 正常验收：两字典独有键全部保留，嵌套x/y合并，冲突按显式策略。
- 异常／边界：循环容器、None、类型冲突、列表重复值、来源对象不改与失败位置。
- 原生回归：新增merge测试；tests/test_delta.py 作语义对照
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．三方合并与冲突报告（增强提案）

- 来源／场景：deepdiff/diff.py 与delta.py的两方模型；固定源码：[deepdiff/diff.py](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/diff.py)、[deepdiff/delta.py](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/delta.py)。
- 原版现状：需调用方自行比较base/left/right并识别双方改动，没有三方API。
- 交付目标：提供merge3(base,left,right)，合并不相交变更，冲突输出路径和三方值。
- 影响模块：新增三方合并模块；Delta与Diff结果
- 兼容边界：默认不自动取一方覆盖冲突；首版JSON树及有明确键策略的数组。
- 正常验收：base两分支分别改region/qty时合并；同一路径改为不同值返回冲突。
- 异常／边界：删除对修改、父子路径重叠、数组移位、相同修改不冲突与输入保持。
- 原生回归：tests/test_delta.py；新增merge3集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．JSON Patch 标准互操作（增强提案）

- 来源／场景：[deepdiff/delta.py:to_flat_dicts/to_flat_rows](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/delta.py)
- 原版现状：有原生Delta和flat表示，无RFC6902 JSON Patch导出/导入契约。
- 交付目标：为JSON数据实现to_json_patch/from_json_patch，使用JSON Pointer转义与稳定数组操作顺序。
- 影响模块：deepdiff/delta.py；path.py；serialization.py
- 兼容边界：非JSON对象/sets/type转换不静默映射成错误patch，明确拒绝；原Delta保持。
- 正常验收：嵌套键含斜杠/波浪号、增删改数组，独立标准操作器应用后得到目标。
- 异常／边界：test失败、越界、move/copy同树路径、空根替换与坏操作结构拒绝。
- 原生回归：tests/test_delta.py；test_path.py；新增JSONPatch集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．不应用补丁的预检报告（增强提案）

- 来源／场景：[deepdiff/delta.py:_do_verify_changes/_raise_or_log](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/delta.py)
- 原版现状：raise_errors和旧值校验已有，但没有一次只读列出所有可应用/冲突位置的公共预检。
- 交付目标：新增Delta.validate_against(base)，返回路径、预期类型/旧值是否匹配及明确错误代码。
- 影响模块：deepdiff/delta.py；path.py
- 兼容边界：不声称预检后外部共享对象不会变化，apply仍需再次核对；不修改base或消费不可重复对象。
- 正常验收：正确base无冲突，陈旧base列出所有旧值不匹配，数据未改。
- 异常／边界：缺父路径、数组长度变化、只读属性、受限类型、多个错误且有上限。
- 原生回归：tests/test_delta.py；test_security.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．多个 Delta 的可验证组合（增强提案）

- 来源／场景：[deepdiff/delta.py:__add__/to_dict](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/delta.py)
- 原版现状：可以顺序base+delta1+delta2，但无合成单一可交付Delta的公共方法。
- 交付目标：增加compose(deltas,base)，验证每段后对base与最终目标生成等价单一Delta。
- 影响模块：deepdiff/delta.py；diff.py
- 兼容边界：要求显式base以正确处理数组索引变化，不伪称任意Delta可无上下文相加。
- 正常验收：组合后的单补丁与顺序应用一致，支持bidirectional时反向回到base。
- 异常／边界：中段冲突全组合拒绝、删除后新增、类型变化、空序列和来源Delta不被改。
- 原生回归：tests/test_delta.py
- 真实依赖：12

## 14．带版本与完整性信息的便携 Delta JSON（增强提案）

- 来源／场景：[deepdiff/delta.py:dump/dumps；serialization.py](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/delta.py)
- 原版现状：可自定义serializer但没有公共版本化JSON封装及类型白名单；默认原生序列化仍有专门规则。
- 交付目标：新增明确portable JSON格式，含schema版本、payload、可选base摘要与受支持类型标签。
- 影响模块：deepdiff/delta.py；serialization.py
- 兼容边界：不导入任意模块或接受任意类标签，不替换已有dump默认；无法保真的类型明确拒绝。
- 正常验收：JSON树/Decimal/date等声明支持子集跨进程读取应用一致，旧值验证保持。
- 异常／边界：未知版本/类型、摘要不符、截断、超大payload和不能表示的函数/对象拒绝。
- 原生回归：tests/test_serialization.py；test_security.py；test_delta.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．比较的时间预算与合作取消（增强提案）

- 来源／场景：[deepdiff/diff.py:_count_diff；max_diffs/max_passes](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/diff.py)
- 原版现状：已有工作计数上限和进度日志，没有monotonic deadline或cancel_check。
- 交付目标：增加max_elapsed/cancel_check，检查递归和无序配对循环，结果明确complete/partial与原因。
- 影响模块：deepdiff/diff.py；deephash.py；并发结果收口
- 兼容边界：默认无时限；不声称能强制中断任意用户operator，不允许partial结果无提示生成完整Delta。
- 正常验收：合成昂贵比较在预算处停止、标注partial，取消不误报空差异等于一致。
- 异常／边界：首次调用取消、长Hash阶段、多进程工作者收口、回调异常与边界时间。
- 原生回归：tests/test_ignore_order.py；test_cache.py；test_multiprocessing.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．逐条差异事件输出（增强提案）

- 来源／场景：[deepdiff/diff.py:_report_result；progress_logger](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/diff.py)
- 原版现状：progress_logger仅计数文本，最终差异集合全部保存；无业务差异sink。
- 交付目标：增加report_sink和store_results=False模式，输出有序差异事件及完成状态。
- 影响模块：deepdiff/diff.py；model.py；serialization.py
- 兼容边界：默认集合返回保持；只降低报告累积成本，不宣称输入/Hash/匹配内存恒定。
- 正常验收：大量订单变更逐条写JSONL，事件重建的text视图等于普通diff。
- 异常／边界：sink失败、截断、ignore_order配对稳定、多进程事件顺序与最终状态不缺失。
- 原生回归：tests/test_diff_text.py；test_serialization.py；test_multiprocessing.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．报告保留路径但遮盖选定值（增强提案）

- 来源／场景：[deepdiff/serialization.py:to_json/to_dict](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/serialization.py)
- 原版现状：exclude_paths会移除差异本身，不能保留路径/type同时将old/new值遮盖。
- 交付目标：新增redact_paths用于展示层，保留差异类别及路径，把匹配值换成明确占位。
- 影响模块：deepdiff/serialization.py；path.py glob匹配
- 兼容边界：不修改内部Diff或可执行Delta；默认不开启，不在日志中输出被遮盖原值。
- 正常验收：合成token变化仍显示values_changed路径，old/new值在JSON/tree展示均无原串。
- 异常／边界：父路径遮盖全部子值、通配、特殊键、类型变化对象和自定义serializer。
- 原生回归：tests/test_serialization.py；test_colored_view.py；test_glob_paths.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．每路径数值容差规则（增强提案）

- 来源／场景：[deepdiff/diff.py:math_epsilon/significant_digits；operator.py](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/diff.py)
- 原版现状：全局容差已有，按路径需自写operator，没有声明式容差表。
- 交付目标：增加numeric_tolerances路径规则，支持绝对/相对容差且明确优先级。
- 影响模块：deepdiff/diff.py；path.py；deephash.py 无序一致性
- 兼容边界：默认全局参数保持；冲突规则明确拒绝，不能比较时绕过type检查。
- 正常验收：金额严格到分、温度允许0.1，不同字段按各自规则报告。
- 异常／边界：0附近相对容差、NaN/Infinity、Decimal、Hash配对与ignore_order不能不一致。
- 原生回归：tests/test_diff_math.py；test_ignore_order.py；test_hash.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．解释路径为何被过滤或粗粒度报告（增强提案）

- 来源／场景：[deepdiff/diff.py:_skip_this/threshold_to_diff_deeper](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/diff.py)
- 原版现状：可观察最终diff，缺少结构化“为什么跳过/为什么整父节点报告”的诊断。
- 交付目标：增加explain_path或diagnostic_sink，输出过滤命中、阈值和operator接管等理由代码。
- 影响模块：deepdiff/diff.py；path.py；operator.py
- 兼容边界：默认不收集值，限制诊断量；诊断不改变过滤结果或重新调用有副作用operator。
- 正常验收：指定路径被exclude、未被include、阈值父层替换都有可解释原因。
- 异常／边界：多个规则同时命中、同名键、无序重排路径、数量上限与回调异常。
- 原生回归：tests/test_diff_include_paths.py；test_glob_paths.py；test_operators.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．CLI 批量比较清单与独立结果（增强提案）

- 来源／场景：[deepdiff/commands.py:diff](https://github.com/qlustered/deepdiff/blob/79e4379278b1cfdd8e9e3dccac364956908e8989/deepdiff/commands.py)
- 原版现状：deep diff只接两个文件，跨多个配置文件需外部脚本管理参数/错误和汇总。
- 交付目标：新增batch命令，读取显式文件对清单与公共配置，逐对输出JSONL摘要及可选报告文件。
- 影响模块：deepdiff/commands.py；serialization.py 文件读取辅助
- 兼容边界：不自动扫描未知目录或访问URL，保留单对命令退出行为；文件格式仍沿已支持集合。
- 正常验收：三对合成JSON/CSV分别equal/changed/error，汇总数与每对报告一致。
- 异常／边界：缺文件、同输出路径、单对失败继续/停止策略、Unicode路径、无列表与只读目标。
- 原生回归：tests/test_command.py；test_serialization.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
