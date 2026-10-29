"""制作工单流转语义、回调集成和失败发布方案。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项事件工作流决策及名称冲突诊断。@return None。"""
    rows = [
        ('TR-U01', 'understand', '解释初始、内部与自循环回调', 'Use Machine(model,states=[state a with on_enter/on_exit log callbacks],initial="a",auto_transitions=False). Compare initialization,an internal a->None event and a reflexive a->a event,each with an after callback. Explain the logs;no edits.',
            'Initialization emits no entry callback. The internal event emits only after;the reflexive event emits exit,enter,after while final state remains a. Choose an internal transition when state entry/exit effects must not repeat;state-name equality alone does not identify the callback lifecycle.', 'initial_internal_and_reflexive_callbacks_have_different_lifecycles'),
        ('TR-U02', 'understand', '解释同事件的候选优先级', 'Register review:a->b with a Boolean guard,then review:a->c unconditionally;disable auto transitions. Compare separate initial models with guard True and False. Explain ordering and fallback. No edits.',
            'The first enabled transition wins:True reaches b;False skips it and reaches c. Registration order is business priority,so an unconditional earlier transition would shadow later candidates. Guards should be side-effect aware and fallback placement explicit;this does not evaluate all targets or merge outcomes.', 'first_enabled_transition_wins_in_registration_order'),
        ('TR-C01', 'consult', '正确解释排队触发的返回值', 'For separate Machine instances with queued=False and queued=True,register go:a->b with an always-false guard and auto_transitions=False. Compare trigger return value and final state. Advise how a UI should confirm a transition. No implementation.',
            'Synchronous mode returns False and stays a;queued mode returns True but also stays a. Queued True indicates accepted processing,not proof a guard passed or state changed. Confirm actual state/transition outcome through explicit completion evidence;do not equate the Boolean return with a completed business operation.', 'queued_trigger_true_does_not_prove_a_guarded_transition_happened'),
        ('TR-C02', 'consult', '明确回调参数集成合同', 'Configure send_event=True on Machine with go:a->b and an after callback record(event). Trigger model.go(ticket="T-1"). Inspect event.event.name,transition source/dest,state.name and kwargs. Advise callback signatures and correlation handling. No edits.',
            'The callback receives EventData,not raw ticket keyword arguments. After transition it reports go,a,b,b and kwargs ticket T-1. Choose one consistent send_event contract and explicitly read correlation data;do not assume an after callback record(ticket) receives the string or that the wrapper persists durable audit records.', 'send_event_passes_eventdata_instead_of_forwarding_raw_callback_kwargs'),
        ('TR-P01', 'plan', '规划回调失败后的状态和副作用处理', 'Machine defaults to propagating callback errors;go:a->b has an on_enter_b callback that logs entry-effect then raises ValueError,and an after callback that logs after. Inspect exception,state and logs. Plan durable publication/retry/recovery. No implementation or real database access.',
            'The exception propagates after state assignment:state is b,entry-effect remains and after does not run. The in-memory machine does not roll back state or arbitrary effects. Plan explicit durable transition/effect ownership,operation identity,completion/error records and recovery/compensation tested at each callback boundary. Do not blindly retry based on the old state or claim atomic database/external effects.', 'entry_callback_failure_does_not_rollback_the_already_assigned_state')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('TR-D01', 'diagnose', '诊断模型同名方法未触发流转', 'A model.go() call returns a business value without changing state. Request the original model attributes,Machine setup,event registration and generic trigger control before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed model-binding evidence to distinguish an existing method name collision from a guard failure or missing transition. Missing evidence supports insufficient_information;do not overwrite a business method or silently rename a published event.', None))
    materials['disclosure/name-collision.md'] = 'Model already has go=lambda:"business". Machine(model,states=["a","b"],initial="a",auto_transitions=False) then add_transition("go","a","b"). model.go() returns "business" and remains a. model.trigger("go") then reaches b. Machine._checked_assignment preserves pre-existing model attributes under the default model_override=False. No guard or asynchronous queue is configured.\n'
    materials['disclosure/unavailable.md'] = 'Original model attributes,Machine configuration,event registration and generic trigger control are unavailable.\n'
    answers.update({'TR-D01-question': 'Please provide the original model method/attributes,Machine setup,exact transition registration and model.trigger control. I need actual binding evidence before diagnosing;no edits are authorized.',
        'TR-D01': 'The existing business go method is preserved by default checked assignment,so model.go calls it rather than the generated event helper. The generic model.trigger("go") control proves the event itself is registered and can transition. Use an explicitly agreed naming/binding convention or the generic trigger at a reviewed caller boundary;do not overwrite the business method or change published event names without scope. No source change was made.',
        'TR-D01-unavailable': 'The model/binding/event controls are unavailable. Record insufficient_information and request them later;no exact cause is established. No changes.'})
    build_project('transitions', {'title': 'Transitions工单流转工作场景', 'category': '事件、回调与失败边界',
        'description': '内部与自循环、守卫优先级、队列返回值、事件参数、回调失败方案及方法绑定诊断。'}, definitions,
        [('TR-S01', '状态流转语义', '明确回调与优先级', ['TR-U01', 'TR-U02']),
         ('TR-S02', '工作流集成咨询', '确认结果与回调参数', ['TR-C01', 'TR-C02']),
         ('TR-S03', '持久业务方案', '界定异常和副作用', ['TR-P01']),
         ('TR-S04', '模型绑定诊断', '取得实际方法与事件证据', ['TR-D01'])], materials,
        branches={'TR-D01': [{'id': 'preexisting-model-method', 'when': 'Model attributes,Machine setup,event registration and generic trigger control have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/name-collision.md']}]},
        extra_entries={'TR-S04': [{'id': 'unavailable', 'task_ids': ['TR-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('transitions-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
