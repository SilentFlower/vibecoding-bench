"""制作真实依赖装配、作用域和配置归属任务。"""
from draft_content import build_project


def main() -> None:
    """冻结四场景六任务，保持只读授权与实际材料分支。@return None。"""
    materials = {
        'materials/services.md': 'Define class Service with an @inject constructor __init__(self,name:str) that stores self.name. Define @singleton class CachedService(Service). A helper constructs a new Injector and binds str to a supplied synthetic name. Use no real configuration,network or service process. All controls are read-only with respect to the supplied library.\n',
        'materials/lifetime.md': 'Create independent Injectors configured with alpha and beta. Resolve Service twice in the first,resolve CachedService repeatedly in the first,and resolve CachedService in the second. Explain actual object identities and names,ordinary NoScope versus singleton scope,and the boundary of the same-container claim. No edits.\n',
        'materials/constructor.md': 'With str explicitly bound to provided,compare direct Service(),Service("direct"),container.create_object(Service),and create_object(Service,additional_kwargs={"name":"explicit"}). Explain which boundary actually performs injection and explicit argument precedence. Do not claim the decorator automatically supplies arguments on an ordinary Python call or rely on undocumented free-function decorator behavior. No edits.\n',
        'materials/config-binding.md': 'Compare permissive Injector().get(Service) with Injector(auto_bind=False) after explicitly binding Service to its class but not binding str. Then bind str to configured and retry the strict container. Distinguish constructor success,automatic default values and business configuration validation. No edits or real application configuration.\n',
        'materials/aggregation.md': 'Use multibind(list[str],to=["alpha"]) then ["beta"]. For dict[str,int],contribute {limit:1,offset:0} then {limit:2}. Append caller-only to one resolved list and resolve it again. Also multibind list[Service] to an existing Service("original") object,mutate that member name to shared and resolve again. Compare ordinary bind(list[str],to=[...]),which is not the collection registration entry. Advise aggregation order,duplicate-key policy and container/member ownership without claiming a deep immutable snapshot. No edits.\n',
        'materials/request-scope-plan.md': 'Define @threadlocal class FlowContext with no real request data. In one Injector,run two async coroutines on the same thread;each gets FlowContext,before and after await asyncio.sleep(0). Separately keep two real worker threads alive with a Barrier and resolve the same class. Plan isolation for logical async requests from these actual identity controls. Choose explicit per-request objects/containers or an application-owned Scope integration,with context entry/exit,child-task inheritance and error cleanup policy. Thread identity is not an async request identity. No implementation or modification of library synchronization.\n',
        'disclosure/rebinding.md': 'Complete synthetic sequence: bind str to old in one Injector;resolve CachedService and retain that object;rebind str to new;resolve CachedService again. Original and later service names are both old,and the object identity is preserved. The current container.get(str) is new;newly resolved ordinary Service has name new;a fresh Injector bound to new constructs CachedService with name new. CachedService carries the supplied @singleton scope and its inherited @inject constructor. No exception occurs. Diagnose binding versus existing-object lifetime and advise explicit initialization/reconfiguration ownership without claiming an automatic cache invalidation API. No edits.\n',
        'disclosure/unavailable.md': 'The binding setup,scope declarations,resolution/rebinding order,object identity and dependency/service values cannot be supplied. No complete reproduction establishes a stale dependency,service cache or configuration source.\n'}
    definitions = [
        ('IJ-U01', 'understand', '明确普通对象与单例的容器归属',
            'Explain the complete lifetime controls with actual identities and configuration names. No edits.',
            ['materials/services.md', 'materials/lifetime.md'], 'explained',
            'Default NoScope produces distinct Service objects with alpha. Repeated CachedService resolution in the same first Injector reuses one alpha object;the separate beta Injector owns a different beta singleton. Distinguish provider/scope lifetime and explicit instance binding from a global process-wide singleton promise.',
            ['no_scope_constructs_while_singleton_caches_per_injector']),
        ('IJ-U02', 'understand', '解释构造器注入的实际调用边界',
            'Explain all complete direct and Injector construction controls,including argument precedence. No edits.',
            ['materials/services.md', 'materials/constructor.md'], 'explained',
            'Direct Service() still raises TypeError for its missing name;the inject decorator declares bindings without replacing normal Python argument requirements. Service(direct) uses its explicit value. create_object obtains provided from the Injector,while additional_kwargs explicit wins. Use the documented construction boundary rather than claim the decorator alone performs a call or a global lookup.',
            ['constructor_injection_requires_the_injector_call_boundary']),
        ('IJ-C01', 'consult', '区分自动构造与有效业务配置',
            'Advise explicit configuration binding from the complete permissive/strict controls. No edits.',
            ['materials/services.md', 'materials/config-binding.md'], 'advice_no_code_change',
            'Permissive auto binding constructs str as an empty string and therefore a Service without meaningful configured data. With Service explicitly bound and auto_bindFalse,the missing str raises UnsatisfiedRequirement;binding it explicitly to configured restores construction. Choose explicit configuration objects/values and business validation;do not mistake successful construction or a type annotation for validated configuration.',
            ['auto_binding_can_construct_default_values_instead_of_configuration']),
        ('IJ-C02', 'consult', '选择插件与配置聚合的覆盖和归属',
            'Advise actual multibinding aggregation,duplicate-key and object ownership behavior from every supplied control. No implementation.',
            ['materials/services.md', 'materials/aggregation.md'], 'advice_no_code_change',
            'Use multibind,not ordinary bind,for reserved generic list/dict keys. The list aggregate preserves alpha,beta contributions and a caller append does not alter a later outer list. Dictionary limit is2 and offset0 because later key contributions overwrite earlier values. An explicitly supplied Service member remains the same mutable object and its shared name is visible later;the fresh outer list is not a deep copy. Own duplicate-key and member lifetime policy explicitly.',
            ['multibinding_aggregation_and_duplicate_key_policy_are_explicit']),
        ('IJ-P01', 'plan', '规划异步请求的对象隔离边界',
            'Plan request-owned dependency lifetime and cleanup using the real coroutine/thread identity controls. No implementation.',
            ['materials/request-scope-plan.md'], 'planned_without_library_change',
            'Both interleaved coroutines on one thread share the same threadlocal FlowContext before and after their yield;two simultaneously live worker threads receive distinct contexts. ThreadLocalScope is per-thread,not per async request. Choose and describe explicit request objects/containers or an application-owned Scope with logical context ownership,entry/exit,child-task inheritance and exception cleanup. Test overlapping async requests and nested/error cases;do not claim an existing automatic request scope or change library locking. Equivalent complete designs are valid.',
            ['thread_local_scope_does_not_isolate_coroutines_on_one_thread']),
        ('IJ-D01', 'diagnose', '先核装配与身份再解释配置未生效',
            'Some resolved services keep old configuration after a rebinding. Request complete bindings,scope declarations,resolution/rebinding order,object identities and values before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually delivered setup and identity evidence. Request missing sequence/scope controls before choosing a cause. Once complete evidence is consumed,trace actual binding resolution and existing-object scope lifetime,contrast current dependency/new-object controls,and advise application-owned initialization or recreation without inventing automatic invalidation. Unavailable evidence supports insufficient_information;no library repair is authorized.', None)]
    scenes = [
        ('IJ-S01', '对象装配与生命周期', '核调用边界和容器归属', ['IJ-U01', 'IJ-U02']),
        ('IJ-S02', '配置与插件绑定', '显式选择有效值和聚合策略', ['IJ-C01', 'IJ-C02']),
        ('IJ-S03', '异步请求归属', '独立定义逻辑请求对象生命周期', ['IJ-P01']),
        ('IJ-S04', '配置更新诊断', '先核完整作用域和身份', ['IJ-D01'])]
    materials['disclosure/services.md'] = materials['materials/services.md']
    build_project('injector', {'title': 'Injector对象装配工作场景', 'category': '配置、对象生命周期与聚合',
        'description': '容器归属、构造注入、有效配置、插件聚合、异步请求和更新诊断六项任务。'},
        definitions, scenes, materials,
        branches={'IJ-D01': [{'id': 'complete-rebinding-reproduction',
            'when': 'The complete bindings,scope declarations,resolution/rebinding sequence and identity/value controls have not been supplied or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/rebinding.md', 'disclosure/services.md']}]},
        extra_entries={'IJ-S04': [{'id': 'unavailable', 'task_ids': ['IJ-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
