"""制作可观察性包装、代理能力与精确撤销的实际任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项包装集成判断；业务直接核Python候选，完整原生另含C。@return None。"""
    rows = [
        ('WR-U01', 'understand', '解释装饰器的方法绑定', 'Use @wrapt.decorator trace(wrapped,instance,args,kwargs) recording then calling wrapped(*args,**kwargs). Decorate Service.calculate(self,x:int,y:int=2)->int returning x+y. Compare service.calculate(3),Service.calculate(service,4),records,inspect.signature(bound method) and __wrapped__. No edits.',
            'Results are5 and6;instance is the service in both calls and args are(3,) and(4,),without an extra self. The bound signature remains(x:int,y:int=2)->int and __wrapped__ identifies calculate. Call the already bound wrapped target with args/kwargs;do not pass instance again or replace the visible signature with generic *args solely for tracing.', 'decorator_binding_separates_instance_and_preserves_the_visible_signature'),
        ('WR-U02', 'understand', '区分代理身份和属性归属', 'Wrap SimpleNamespace(name="first") in BaseObjectProxy;assign proxy.name="second" and proxy._self_note="local". Compare wrapped identity and attributes. Also compare isinstance(ObjectProxy(1),int) with type(proxy) is int for that numeric proxy. No edits.',
            'Normal name assignment reaches the wrapped object;_self_ prefixed state belongs to the proxy and is absent from the wrapped object. __wrapped__ is the original object. Numeric ObjectProxy passes isinstance(...,int) but its concrete type is a proxy,so identity,type and delegated behavior are distinct. Choose explicit introspection and state ownership;do not treat a proxy as a deep copy.', 'proxy_identity_attribute_delegation_and_local_namespace_are_distinct'),
        ('WR-C01', 'consult', '评估代理的可迭代能力检测', 'Compare isinstance(...,collections.abc.Iterable) and actual list consumption for ObjectProxy(1) and BaseObjectProxy(1). Advise a protocol-compatible proxy choice without adding methods or changing code.',
            'Legacy ObjectProxy exposes __iter__,so Iterable detection is True even around an int;BaseObjectProxy does not expose that compatibility method and detection is False. Both integer-wrapped controls fail actual list consumption with TypeError. BaseObjectProxy or a reviewed explicit protocol proxy avoids this legacy false-positive surface;do not assume an advertised method proves the wrapped value supports its operation or that iter() creation alone completes consumption.', 'legacy_objectproxy_iterable_detection_can_overstate_wrapped_capability'),
        ('WR-C02', 'consult', '选择运行时观测开关', 'Use @wrapt.decorator(enabled=lambda:flag["value"]) around a target returning value+1;the wrapper records audit then calls the target. Compare calls with flag False then True. Advise instrumentation enablement and side-effect boundaries. No implementation.',
            'Both calls return2 for input1,while only the enabled call records audit. A callable enabled policy can select instrumentation dynamically for this ordinary function control. Define a consistent policy/lifecycle and test bound-method timing separately;disabling instrumentation does not disable the underlying business call or authorize skipping required business validation.', 'dynamic_decorator_enablement_changes_instrumentation_without_changing_the_target_result'),
        ('WR-P01', 'plan', '规划只撤销本方的函数包装', 'On a local namespace calculate(x)=x+1,install an inner wrapper multiplying the result by2 and outer wrapper adding3 using wrap_function_wrapper. Save both returned handles;remove inner then outer with unwrap_object. Inspect calculate(2) after each step. Plan plugin lifecycle and failure handling without patching real modules.',
            'Results are9 with both layers,6 after removing inner while preserving outer,and3 after removing outer. Save the actual returned wrapper identity handle;do not pass the callback function or reset the attribute to an old snapshot that discards others. Pair install/removal in a controlled lifecycle,handle missing/replaced/non-spliceable layers explicitly,and test nested/inherited/deferred cases relevant to the caller. This plan does not authorize process-wide monkeypatching.', 'identity_handles_remove_only_the_owned_wrapper_and_preserve_other_layers')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' Business observations bind actual candidate Python source;the complete original regression separately verifies forced C builds and Python mode. No changes were made.'
    definitions.append(('WR-D01', 'diagnose', '诊断导入钩子为何立即执行', 'A post-import hook fires during registration instead of a later explicit import. Request module identity,sys.modules presence,registration/import sequence and hook observations before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed import-order evidence to distinguish an already loaded module from a future deferred import. Missing evidence supports insufficient_information;do not delete unrelated sys.modules entries,reload modules or promise import hooks are always deferred.', None))
    materials['disclosure/already-imported.md'] = 'An isolated local ModuleType named pack_local_plugin_probe is already in sys.modules before register_post_import_hook(hook,"pack_local_plugin_probe"). Registration immediately invokes hook with that identical module;the counter is1 before any later import statement. No asynchronous importer,real plugin or module reload is involved. Source register_post_import_hook checks sys.modules and calls an already-loaded module hook outside its lock.\n'
    materials['disclosure/unavailable.md'] = 'Module identity,sys.modules presence,registration/import order and hook observations are unavailable.\n'
    answers.update({'WR-D01-question': 'Please provide the module identity,its sys.modules presence at registration,the complete registration/import sequence and hook observations. No changes are authorized.',
        'WR-D01': 'The supplied module is already loaded,so register_post_import_hook invokes the hook immediately with that module,as documented by the source branch outside the lock. Only an unloaded module gets a future-import registration. Make instrumentation setup ready before registration and design an idempotent initialization lifecycle;do not delete unrelated module entries or reload real plugins to force the timing. No source change was made.',
        'WR-D01-unavailable': 'The module/order/hook controls are unavailable. Record insufficient_information and request them later;an exact timing cause is not established. No edits.'})
    build_project('wrapt', {'title': 'Wrapt可观察性集成工作场景', 'category': '装饰、代理与包装生命周期',
        'description': '方法绑定、代理身份、协议检测、观测开关、句柄撤销方案及导入时序诊断。'}, definitions,
        [('WR-S01', '装饰与代理语义', '明确绑定和属性归属', ['WR-U01', 'WR-U02']),
         ('WR-S02', '观测集成咨询', '选择协议与开关合同', ['WR-C01', 'WR-C02']),
         ('WR-S03', '包装生命周期方案', '只撤销明确持有的包装', ['WR-P01']),
         ('WR-S04', '导入时序诊断', '取得模块实际状态', ['WR-D01'])], materials,
        branches={'WR-D01': [{'id': 'module-already-loaded', 'when': 'Module identity,sys.modules presence,registration/import order and hook controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/already-imported.md']}]},
        extra_entries={'WR-S04': [{'id': 'unavailable', 'task_ids': ['WR-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('wrapt-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
