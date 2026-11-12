"""核事件流转、回调、排队和状态失败边界。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from types import SimpleNamespace

import transitions
from transitions import Machine


def main() -> None:
    """使用本地模型核本次候选，不连接真实工作流或数据库。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(transitions.__file__).resolve() == root / 'library/transitions/__init__.py'}
    task = argv[1]
    if task == 'TR-U01':
        events, model = [], SimpleNamespace()
        machine = Machine(model, states=[{'name': 'a', 'on_enter': lambda: events.append('enter'),
            'on_exit': lambda: events.append('exit')}], initial='a', auto_transitions=False)
        initial = list(events)
        machine.add_transition('inside', 'a', None, after=lambda: events.append('after'))
        machine.add_transition('again', 'a', 'a', after=lambda: events.append('after'))
        model.inside()
        internal = list(events)
        events.clear()
        model.again()
        result['initial_internal_and_reflexive_callbacks_have_different_lifecycles'] = (
            initial == [] and internal == ['after'] and events == ['exit', 'enter', 'after'] and model.state == 'a')
    elif task == 'TR-U02':
        destinations = []
        for guard in (True, False):
            model = SimpleNamespace()
            machine = Machine(model, states=['a', 'b', 'c'], initial='a', auto_transitions=False)
            machine.add_transition('review', 'a', 'b', conditions=lambda: guard)
            machine.add_transition('review', 'a', 'c')
            model.review()
            destinations.append(model.state)
        result['first_enabled_transition_wins_in_registration_order'] = destinations == ['b', 'c']
    elif task == 'TR-C01':
        values = []
        for queued in (False, True):
            model = SimpleNamespace()
            machine = Machine(model, states=['a', 'b'], initial='a', auto_transitions=False, queued=queued)
            machine.add_transition('go', 'a', 'b', conditions=lambda: False)
            values.append((model.go(), model.state))
        result['queued_trigger_true_does_not_prove_a_guarded_transition_happened'] = values == [(False, 'a'), (True, 'a')]
    elif task == 'TR-C02':
        model, events = SimpleNamespace(), []
        machine = Machine(model, states=['a', 'b'], initial='a', auto_transitions=False, send_event=True)

        def record(event):
            """记录实际事件包装参数。@param event 当前EventData。@return None。"""
            events.append((event.event.name, event.transition.source, event.transition.dest,
                event.state.name, event.kwargs['ticket']))

        machine.add_transition('go', 'a', 'b', after=record)
        model.go(ticket='T-1')
        result['send_event_passes_eventdata_instead_of_forwarding_raw_callback_kwargs'] = events == [('go', 'a', 'b', 'b', 'T-1')]
    elif task == 'TR-P01':
        model, events = SimpleNamespace(), []

        def enter():
            """模拟进入状态后失败，不执行真实外部操作。@return None。"""
            events.append('entry-effect')
            raise ValueError('entry failed')

        machine = Machine(model, states=['a', {'name': 'b', 'on_enter': enter}], initial='a', auto_transitions=False)
        machine.add_transition('go', 'a', 'b', after=lambda: events.append('after'))
        raised = False
        try:
            model.go()
        except ValueError:
            raised = True
        result['entry_callback_failure_does_not_rollback_the_already_assigned_state'] = (
            raised and model.state == 'b' and events == ['entry-effect'])
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
