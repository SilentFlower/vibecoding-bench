"""核装饰器绑定、代理身份和按句柄撤销包装的真实业务行为。"""
from collections.abc import Iterable
from inspect import signature
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from types import SimpleNamespace

# 业务观察直接导入候选Python源码；完整原生已另核真实C构建及Python两套入口。
environ['WRAPT_DISABLE_EXTENSIONS'] = '1'
import wrapt
from wrapt import __wrapt__ as mode


def main() -> None:
    """只在本地自建对象上包裹函数，保持外部模块不变。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(wrapt.__file__).resolve() == root / 'library/src/wrapt/__init__.py'
        and not mode._using_c_extension}
    task = argv[1]
    if task == 'WR-U01':
        calls = []

        @wrapt.decorator
        def trace(wrapped, instance, args, kwargs):
            """记录绑定实例和未重复携带self的参数。@param wrapped 原函数。@param instance 实例。@param args 参数。@param kwargs 关键参数。@return 原结果。"""
            calls.append((instance, args, kwargs))
            return wrapped(*args, **kwargs)

        class Service:
            """本地示例业务服务。"""
            @trace
            def calculate(self, x: int, y: int = 2) -> int:
                """计算示例值。@param x 加数。@param y 加数。@return 和。"""
                return x + y

        service = Service()
        values = [service.calculate(3), Service.calculate(service, 4)]
        result['decorator_binding_separates_instance_and_preserves_the_visible_signature'] = (
            values == [5, 6] and calls == [(service, (3,), {}), (service, (4,), {})]
            and str(signature(service.calculate)) == '(x: int, y: int = 2) -> int'
            and service.calculate.__wrapped__.__name__ == 'calculate')
    elif task == 'WR-U02':
        original = SimpleNamespace(name='first')
        proxy = wrapt.BaseObjectProxy(original)
        proxy.name = 'second'
        proxy._self_note = 'local'
        numeric = wrapt.ObjectProxy(1)
        result['proxy_identity_attribute_delegation_and_local_namespace_are_distinct'] = (
            proxy.__wrapped__ is original and original.name == 'second' and proxy._self_note == 'local'
            and not hasattr(original, '_self_note') and isinstance(numeric, int) and type(numeric) is not int)
    elif task == 'WR-C01':
        legacy, base = wrapt.ObjectProxy(1), wrapt.BaseObjectProxy(1)
        rejected = []
        for proxy in (legacy, base):
            try:
                list(proxy)
                rejected.append(False)
            except TypeError:
                rejected.append(True)
        result['legacy_objectproxy_iterable_detection_can_overstate_wrapped_capability'] = (
            isinstance(legacy, Iterable) and not isinstance(base, Iterable) and all(rejected))
    elif task == 'WR-C02':
        enabled, events = {'value': False}, []

        @wrapt.decorator(enabled=lambda: enabled['value'])
        def audit(wrapped, instance, args, kwargs):
            """按明确开关记录调用。@param wrapped 原函数。@param instance 实例。@param args 参数。@param kwargs 关键参数。@return 原结果。"""
            events.append('audit')
            return wrapped(*args, **kwargs)

        @audit
        def target(value):
            """保持业务结果不变。@param value 输入。@return 加一。"""
            return value + 1

        before = target(1)
        silent = list(events)
        enabled['value'] = True
        after = target(1)
        result['dynamic_decorator_enablement_changes_instrumentation_without_changing_the_target_result'] = (
            before == after == 2 and silent == [] and events == ['audit'])
    elif task == 'WR-P01':
        namespace = SimpleNamespace(calculate=lambda value: value + 1)

        def double(wrapped, instance, args, kwargs):
            """第一层示例包装。@param wrapped 原函数。@param instance 实例。@param args 参数。@param kwargs 关键参数。@return 两倍。"""
            return wrapped(*args, **kwargs) * 2

        def extra(wrapped, instance, args, kwargs):
            """第二层示例包装。@param wrapped 原函数。@param instance 实例。@param args 参数。@param kwargs 关键参数。@return 加三。"""
            return wrapped(*args, **kwargs) + 3

        inner = wrapt.wrap_function_wrapper(namespace, 'calculate', double)
        outer = wrapt.wrap_function_wrapper(namespace, 'calculate', extra)
        both = namespace.calculate(2)
        wrapt.unwrap_object(namespace, 'calculate', inner)
        remaining = namespace.calculate(2)
        wrapt.unwrap_object(namespace, 'calculate', outer)
        result['identity_handles_remove_only_the_owned_wrapper_and_preserve_other_layers'] = (
            (both, remaining, namespace.calculate(2)) == (9, 6, 3))
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
