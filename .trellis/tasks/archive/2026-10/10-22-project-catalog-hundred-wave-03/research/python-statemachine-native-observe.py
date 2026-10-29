"""核领域模型、条件与校验器、保留名称和异步初始激活。"""
import asyncio
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from types import SimpleNamespace

import statemachine
from statemachine import State, StateChart, StateMachine
from statemachine.exceptions import TransitionNotAllowed


class OrderMachine(StateMachine):
    """只用于本地业务控制的订单状态定义。"""
    pending = State(initial=True, value='new')
    done = State(final=True, value='ok')
    finish = pending.to(done)


def main() -> None:
    """以确定状态及调用控制核本次候选，不操作真实工作流。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(statemachine.__file__).resolve() == root / 'library/statemachine/__init__.py'}
    task = argv[1]
    if task == 'SM-U01':
        model = SimpleNamespace(status='new')
        machine = OrderMachine(model, state_field='status')
        initial = list(machine.configuration_values)
        machine.finish()
        result['declared_state_values_update_the_selected_domain_model_field'] = (
            initial == ['new'] and model.status == 'ok' and list(machine.configuration_values) == ['ok']
            and machine.model is model)
    elif task == 'SM-U02':
        class Guarded(StateMachine):
            """以返回False的条件阻止转换。"""
            pending = State(initial=True)
            done = State(final=True)
            finish = pending.to(done, cond='check')

            def check(self):
                """条件返回拒绝。@return False。"""
                return False

        class Validated(StateMachine):
            """校验器需要抛错，返回False不代表拒绝。"""
            pending = State(initial=True)
            done = State(final=True)
            finish = pending.to(done, validators='check')

            def check(self):
                """返回值不构成校验失败。@return False。"""
                return False

        guarded, validated, rejected = Guarded(), Validated(), False
        try:
            guarded.finish()
        except TransitionNotAllowed:
            rejected = True
        validated.finish()
        result['false_guard_blocks_but_false_validator_return_does_not_veto'] = (
            rejected and list(guarded.configuration_values) == ['pending']
            and list(validated.configuration_values) == ['done'])
    elif task == 'SM-C01':
        class Chart(StateChart):
            """使用StateChart的宽容未知事件默认值。"""
            pending = State(initial=True)
            done = State(final=True)
            finish = pending.to(done)

        chart, strict, rejected = Chart(), OrderMachine(), False
        tolerated = chart.send('unknown')
        try:
            strict.send('unknown')
        except TransitionNotAllowed:
            rejected = True
        result['statechart_and_compatibility_statemachine_have_distinct_unknown_event_defaults'] = (
            tolerated is None and list(chart.configuration_values) == ['pending'] and rejected
            and list(strict.configuration_values) == ['new'])
    elif task == 'SM-C02':
        model = SimpleNamespace(status='new', events=[])
        machine, rejected = OrderMachine(model, state_field='status'), False
        try:
            machine.events = []
        except AttributeError:
            rejected = True
        machine.model.events.append('domain-audit')
        result['domain_data_must_not_replace_framework_reserved_event_properties'] = (
            rejected and model.events == ['domain-audit'] and len(machine.events) == 1
            and str(machine.events[0]) == 'finish')
    elif task == 'SM-P01':
        class AsyncOrder(StateChart):
            """异步回调选择异步引擎。"""
            pending = State(initial=True)
            done = State(final=True)
            finish = pending.to(done)

            async def on_finish(self):
                """返回当前事件的结果。@return 42。"""
                return 42

        async def observe():
            """在同一事件循环中观察真正初始化时点。@return 初始、激活和完成事实。"""
            machine = AsyncOrder()
            before = list(machine.configuration_values)
            await machine.activate_initial_state()
            active = list(machine.configuration_values)
            answer = await machine.finish()
            return before, active, answer, list(machine.configuration_values)

        result['async_construction_requires_activation_before_initial_configuration_is_ready'] = (
            asyncio.run(observe()) == ([], ['pending'], 42, ['done']))
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
