"""制作领域状态值、校验、框架集成和异步就绪的真实任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项与本版本真实公开合同一致的任务。@return None。"""
    rows = [
        ('SM-U01', 'understand', '解释领域状态值和存储字段', 'Declare StateMachine pending=State(initial=True,value="new"),done=State(final=True,value="ok"),finish=pending.to(done). Bind SimpleNamespace(status="new") with state_field="status". Compare configuration_values and model.status before/after finish. No edits.',
            'The active values are new then ok,and the supplied model.status is updated to ok;state IDs pending/done differ from their declared values. The machine uses the selected domain model field and same model identity. This is an in-memory assignment,not proof a database or audit record was persisted.', 'declared_state_values_update_the_selected_domain_model_field'),
        ('SM-U02', 'understand', '区分条件与校验器的失败协议', 'For separate StateMachine definitions with pending initial and done final,attach a callback returning False as cond="check" or validators="check" on finish. Compare outcome,state and exceptions. No other callbacks are installed. No edits.',
            'The false condition leaves pending and StateMachine raises TransitionNotAllowed because no transition is enabled. A validator returning False does not veto:it must raise to signal failure,so this control reaches done. Use guards for Boolean enablement and validators for explicit validation exceptions;do not assume their return protocols match.', 'false_guard_blocks_but_false_validator_return_does_not_veto'),
        ('SM-C01', 'consult', '明确未知事件的兼容策略', 'Compare fresh StateChart and StateMachine definitions with one pending->done event when send("unknown") is called. Advise strict command validation versus tolerant event handling for this pinned version. No implementation.',
            'StateChart tolerates the unknown event,returns None and retains its state;StateMachine raises TransitionNotAllowed and retains state. Select the actual class/class-attribute policy deliberately and validate incoming command identity when required. Tolerance is not proof a business operation occurred;do not generalize defaults between the two classes.', 'statechart_and_compatibility_statemachine_have_distinct_unknown_event_defaults'),
        ('SM-C02', 'consult', '避免领域数据覆盖框架事件属性', 'Use the supplied one-event StateMachine with domain model SimpleNamespace(status="new",events=[]),state_field="status". Compare attempting machine.events=[] with appending to machine.model.events. Advise naming/ownership for an audit list. No edits.',
            'machine.events is the framework read-only bound-event property;assignment raises AttributeError. The separately supplied domain model.events list can hold domain-audit while the framework property still lists finish. Keep business state in an explicit domain model or non-conflicting declared field,inspect reserved names before integration,and do not alter framework properties. The list is not a durable audit service.', 'domain_data_must_not_replace_framework_reserved_event_properties'),
        ('SM-P01', 'plan', '规划异步状态机的就绪发布', 'A StateChart has pending initial,done final,finish=pending.to(done),and async on_finish returning42. Inside a running event loop,inspect configuration_values immediately after construction,after await activate_initial_state(),and after await finish(). Plan UI/service readiness and error handling;no implementation.',
            'Construction inside the loop initially exposes empty configuration;explicit activation yields pending;awaited finish returns42 and reaches done. Publish readiness only after awaited activation when reading initial state,await event completion,and retain errors before advertising success. The first event can activate implicitly,but that does not make immediate post-construction reads ready. Define separate durable publication and concurrency ownership;this local lifecycle is not persistence or cross-process locking.', 'async_construction_requires_activation_before_initial_configuration_is_ready')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('SM-D01', 'diagnose', '诊断旧构造参数未改变事件策略', 'A migration passes allow_event_without_transition=True to a StateMachine constructor but an unknown event still raises. Request pinned version,complete constructor,class attributes and exact send/exception controls. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed version/signature/class-policy evidence to explain constructor kwargs versus the current class attribute. Missing evidence supports insufficient_information. Propose a separately scoped class/caller migration with tests,not a package patch or a claim the option took effect.', None))
    materials['disclosure/class-policy.md'] = 'Pinned3.2.2 StateMachine subclass has pending initial,done final,finish=pending.to(done). Instantiate MachineClass(allow_event_without_transition=True);machine.allow_event_without_transition remains False and machine.send("unknown") raises TransitionNotAllowed. __init__ accepts **kwargs for callback/initial activation data;StateMachine defines the policy as a class attribute. docs/releases/2.0.0.md explicitly skips the old constructor-option example because since3.0.0 it is a class attribute.\n'
    materials['disclosure/unavailable.md'] = 'Pinned version,constructor,class attributes and exact event/exception controls are unavailable.\n'
    answers.update({'SM-D01-question': 'Please provide the pinned package version,complete constructor,class attributes and exact send/exception controls. I need actual signature/policy evidence before diagnosing;no edits are authorized.',
        'SM-D01': 'In this pinned version the policy is a class attribute;the constructor extra keyword is callback/activation data and does not override that attribute. The supplied remaining False value and TransitionNotAllowed confirm it. Migrate through an explicitly reviewed class policy or choose the appropriate supported class,then test known/unknown events and callback inputs. The historical release example is explicitly skipped after3.0.0;do not restore it as a current constructor contract. No package changes were made.',
        'SM-D01-unavailable': 'The version/constructor/class/event controls are unavailable. Record insufficient_information and request them later;the migration cause is unproven. No edits.'})
    build_project('python-statemachine', {'title': 'Python状态机领域集成工作场景', 'category': '状态值、校验与异步就绪',
        'description': '领域字段、条件与校验器、未知事件、保留名称、异步激活方案及旧配置迁移诊断。'}, definitions,
        [('SM-S01', '领域状态合同', '区分值和验证协议', ['SM-U01', 'SM-U02']),
         ('SM-S02', '框架集成咨询', '明确事件策略及名称所有权', ['SM-C01', 'SM-C02']),
         ('SM-S03', '异步就绪方案', '等待真正完成后发布', ['SM-P01']),
         ('SM-S04', '版本迁移诊断', '核当前构造与类策略', ['SM-D01'])], materials,
        branches={'SM-D01': [{'id': 'class-policy-migration', 'when': 'Pinned version,constructor,class policy and event/exception controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/class-policy.md']}]},
        extra_entries={'SM-S04': [{'id': 'unavailable', 'task_ids': ['SM-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('python-statemachine-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
