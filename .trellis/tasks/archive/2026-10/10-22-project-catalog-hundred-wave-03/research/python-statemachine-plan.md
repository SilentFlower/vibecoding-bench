# python-statemachine实际场景任务表

固定来源：https://github.com/fgmacedo/python-statemachine@ec5d8173f740b37941818df13727db9d64ef498d。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## SM-U01：解释领域状态值和存储字段

类型：understand；合法结果：explained。

用户问题与当前控制：Declare StateMachine pending=State(initial=True,value="new"),done=State(final=True,value="ok"),finish=pending.to(done). Bind SimpleNamespace(status="new") with state_field="status". Compare configuration_values and model.status before/after finish. No edits.

独立验收：The active values are new then ok,and the supplied model.status is updated to ok;state IDs pending/done differ from their declared values. The machine uses the selected domain model field and same model identity. This is an in-memory assignment,not proof a database or audit record was persisted.

公开材料：materials/sm-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：declared_state_values_update_the_selected_domain_model_field。

## SM-U02：区分条件与校验器的失败协议

类型：understand；合法结果：explained。

用户问题与当前控制：For separate StateMachine definitions with pending initial and done final,attach a callback returning False as cond="check" or validators="check" on finish. Compare outcome,state and exceptions. No other callbacks are installed. No edits.

独立验收：The false condition leaves pending and StateMachine raises TransitionNotAllowed because no transition is enabled. A validator returning False does not veto:it must raise to signal failure,so this control reaches done. Use guards for Boolean enablement and validators for explicit validation exceptions;do not assume their return protocols match.

公开材料：materials/sm-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：false_guard_blocks_but_false_validator_return_does_not_veto。

## SM-C01：明确未知事件的兼容策略

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Compare fresh StateChart and StateMachine definitions with one pending->done event when send("unknown") is called. Advise strict command validation versus tolerant event handling for this pinned version. No implementation.

独立验收：StateChart tolerates the unknown event,returns None and retains its state;StateMachine raises TransitionNotAllowed and retains state. Select the actual class/class-attribute policy deliberately and validate incoming command identity when required. Tolerance is not proof a business operation occurred;do not generalize defaults between the two classes.

公开材料：materials/sm-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：statechart_and_compatibility_statemachine_have_distinct_unknown_event_defaults。

## SM-C02：避免领域数据覆盖框架事件属性

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Use the supplied one-event StateMachine with domain model SimpleNamespace(status="new",events=[]),state_field="status". Compare attempting machine.events=[] with appending to machine.model.events. Advise naming/ownership for an audit list. No edits.

独立验收：machine.events is the framework read-only bound-event property;assignment raises AttributeError. The separately supplied domain model.events list can hold domain-audit while the framework property still lists finish. Keep business state in an explicit domain model or non-conflicting declared field,inspect reserved names before integration,and do not alter framework properties. The list is not a durable audit service.

公开材料：materials/sm-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：domain_data_must_not_replace_framework_reserved_event_properties。

## SM-P01：规划异步状态机的就绪发布

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：A StateChart has pending initial,done final,finish=pending.to(done),and async on_finish returning42. Inside a running event loop,inspect configuration_values immediately after construction,after await activate_initial_state(),and after await finish(). Plan UI/service readiness and error handling;no implementation.

独立验收：Construction inside the loop initially exposes empty configuration;explicit activation yields pending;awaited finish returns42 and reaches done. Publish readiness only after awaited activation when reading initial state,await event completion,and retain errors before advertising success. The first event can activate implicitly,but that does not make immediate post-construction reads ready. Define separate durable publication and concurrency ownership;this local lifecycle is not persistence or cross-process locking.

公开材料：materials/sm-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：async_construction_requires_activation_before_initial_configuration_is_ready。

## SM-D01：诊断旧构造参数未改变事件策略

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A migration passes allow_event_without_transition=True to a StateMachine constructor but an unknown event still raises. Request pinned version,complete constructor,class attributes and exact send/exception controls. No edits.

独立验收：Use consumed version/signature/class-policy evidence to explain constructor kwargs versus the current class attribute. Missing evidence supports insufficient_information. Propose a separately scoped class/caller migration with tests,not a package patch or a claim the option took effect.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
