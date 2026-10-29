# transitions实际场景任务表

固定来源：https://github.com/pytransitions/transitions@bd42b38f3627e6bca7274fb4d9af2e105f75da7c。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## TR-U01：解释初始、内部与自循环回调

类型：understand；合法结果：explained。

用户问题与当前控制：Use Machine(model,states=[state a with on_enter/on_exit log callbacks],initial="a",auto_transitions=False). Compare initialization,an internal a->None event and a reflexive a->a event,each with an after callback. Explain the logs;no edits.

独立验收：Initialization emits no entry callback. The internal event emits only after;the reflexive event emits exit,enter,after while final state remains a. Choose an internal transition when state entry/exit effects must not repeat;state-name equality alone does not identify the callback lifecycle.

公开材料：materials/tr-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：initial_internal_and_reflexive_callbacks_have_different_lifecycles。

## TR-U02：解释同事件的候选优先级

类型：understand；合法结果：explained。

用户问题与当前控制：Register review:a->b with a Boolean guard,then review:a->c unconditionally;disable auto transitions. Compare separate initial models with guard True and False. Explain ordering and fallback. No edits.

独立验收：The first enabled transition wins:True reaches b;False skips it and reaches c. Registration order is business priority,so an unconditional earlier transition would shadow later candidates. Guards should be side-effect aware and fallback placement explicit;this does not evaluate all targets or merge outcomes.

公开材料：materials/tr-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：first_enabled_transition_wins_in_registration_order。

## TR-C01：正确解释排队触发的返回值

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：For separate Machine instances with queued=False and queued=True,register go:a->b with an always-false guard and auto_transitions=False. Compare trigger return value and final state. Advise how a UI should confirm a transition. No implementation.

独立验收：Synchronous mode returns False and stays a;queued mode returns True but also stays a. Queued True indicates accepted processing,not proof a guard passed or state changed. Confirm actual state/transition outcome through explicit completion evidence;do not equate the Boolean return with a completed business operation.

公开材料：materials/tr-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：queued_trigger_true_does_not_prove_a_guarded_transition_happened。

## TR-C02：明确回调参数集成合同

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Configure send_event=True on Machine with go:a->b and an after callback record(event). Trigger model.go(ticket="T-1"). Inspect event.event.name,transition source/dest,state.name and kwargs. Advise callback signatures and correlation handling. No edits.

独立验收：The callback receives EventData,not raw ticket keyword arguments. After transition it reports go,a,b,b and kwargs ticket T-1. Choose one consistent send_event contract and explicitly read correlation data;do not assume an after callback record(ticket) receives the string or that the wrapper persists durable audit records.

公开材料：materials/tr-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：send_event_passes_eventdata_instead_of_forwarding_raw_callback_kwargs。

## TR-P01：规划回调失败后的状态和副作用处理

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：Machine defaults to propagating callback errors;go:a->b has an on_enter_b callback that logs entry-effect then raises ValueError,and an after callback that logs after. Inspect exception,state and logs. Plan durable publication/retry/recovery. No implementation or real database access.

独立验收：The exception propagates after state assignment:state is b,entry-effect remains and after does not run. The in-memory machine does not roll back state or arbitrary effects. Plan explicit durable transition/effect ownership,operation identity,completion/error records and recovery/compensation tested at each callback boundary. Do not blindly retry based on the old state or claim atomic database/external effects.

公开材料：materials/tr-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：entry_callback_failure_does_not_rollback_the_already_assigned_state。

## TR-D01：诊断模型同名方法未触发流转

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A model.go() call returns a business value without changing state. Request the original model attributes,Machine setup,event registration and generic trigger control before diagnosing. No edits.

独立验收：Use consumed model-binding evidence to distinguish an existing method name collision from a guard failure or missing transition. Missing evidence supports insufficient_information;do not overwrite a business method or silently rename a published event.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
