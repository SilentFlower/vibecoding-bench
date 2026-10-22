# wrapt实际场景任务表

固定来源：https://github.com/GrahamDumpleton/wrapt@6b4e844950213118b19e613248d2bc9469eb731e。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## WR-U01：解释装饰器的方法绑定

类型：understand；合法结果：explained。

用户问题与当前控制：Use @wrapt.decorator trace(wrapped,instance,args,kwargs) recording then calling wrapped(*args,**kwargs). Decorate Service.calculate(self,x:int,y:int=2)->int returning x+y. Compare service.calculate(3),Service.calculate(service,4),records,inspect.signature(bound method) and __wrapped__. No edits.

独立验收：Results are5 and6;instance is the service in both calls and args are(3,) and(4,),without an extra self. The bound signature remains(x:int,y:int=2)->int and __wrapped__ identifies calculate. Call the already bound wrapped target with args/kwargs;do not pass instance again or replace the visible signature with generic *args solely for tracing.

公开材料：materials/wr-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：decorator_binding_separates_instance_and_preserves_the_visible_signature。

## WR-U02：区分代理身份和属性归属

类型：understand；合法结果：explained。

用户问题与当前控制：Wrap SimpleNamespace(name="first") in BaseObjectProxy;assign proxy.name="second" and proxy._self_note="local". Compare wrapped identity and attributes. Also compare isinstance(ObjectProxy(1),int) with type(proxy) is int for that numeric proxy. No edits.

独立验收：Normal name assignment reaches the wrapped object;_self_ prefixed state belongs to the proxy and is absent from the wrapped object. __wrapped__ is the original object. Numeric ObjectProxy passes isinstance(...,int) but its concrete type is a proxy,so identity,type and delegated behavior are distinct. Choose explicit introspection and state ownership;do not treat a proxy as a deep copy.

公开材料：materials/wr-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：proxy_identity_attribute_delegation_and_local_namespace_are_distinct。

## WR-C01：评估代理的可迭代能力检测

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Compare isinstance(...,collections.abc.Iterable) and actual list consumption for ObjectProxy(1) and BaseObjectProxy(1). Advise a protocol-compatible proxy choice without adding methods or changing code.

独立验收：Legacy ObjectProxy exposes __iter__,so Iterable detection is True even around an int;BaseObjectProxy does not expose that compatibility method and detection is False. Both integer-wrapped controls fail actual list consumption with TypeError. BaseObjectProxy or a reviewed explicit protocol proxy avoids this legacy false-positive surface;do not assume an advertised method proves the wrapped value supports its operation or that iter() creation alone completes consumption.

公开材料：materials/wr-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：legacy_objectproxy_iterable_detection_can_overstate_wrapped_capability。

## WR-C02：选择运行时观测开关

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Use @wrapt.decorator(enabled=lambda:flag["value"]) around a target returning value+1;the wrapper records audit then calls the target. Compare calls with flag False then True. Advise instrumentation enablement and side-effect boundaries. No implementation.

独立验收：Both calls return2 for input1,while only the enabled call records audit. A callable enabled policy can select instrumentation dynamically for this ordinary function control. Define a consistent policy/lifecycle and test bound-method timing separately;disabling instrumentation does not disable the underlying business call or authorize skipping required business validation.

公开材料：materials/wr-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：dynamic_decorator_enablement_changes_instrumentation_without_changing_the_target_result。

## WR-P01：规划只撤销本方的函数包装

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：On a local namespace calculate(x)=x+1,install an inner wrapper multiplying the result by2 and outer wrapper adding3 using wrap_function_wrapper. Save both returned handles;remove inner then outer with unwrap_object. Inspect calculate(2) after each step. Plan plugin lifecycle and failure handling without patching real modules.

独立验收：Results are9 with both layers,6 after removing inner while preserving outer,and3 after removing outer. Save the actual returned wrapper identity handle;do not pass the callback function or reset the attribute to an old snapshot that discards others. Pair install/removal in a controlled lifecycle,handle missing/replaced/non-spliceable layers explicitly,and test nested/inherited/deferred cases relevant to the caller. This plan does not authorize process-wide monkeypatching.

公开材料：materials/wr-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：identity_handles_remove_only_the_owned_wrapper_and_preserve_other_layers。

## WR-D01：诊断导入钩子为何立即执行

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A post-import hook fires during registration instead of a later explicit import. Request module identity,sys.modules presence,registration/import sequence and hook observations before diagnosing. No edits.

独立验收：Use consumed import-order evidence to distinguish an already loaded module from a future deferred import. Missing evidence supports insufficient_information;do not delete unrelated sys.modules entries,reload modules or promise import hooks are always deferred.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
