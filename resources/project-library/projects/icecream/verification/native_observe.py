"""观察IceCream返回值、禁用边界、格式化与输出配置所有权。"""
from __future__ import annotations

from inspect import getfile
import json
import os
from pathlib import Path
import sys

from icecream import IceCreamDebugger


def passthrough() -> dict:
    """核调试调用返回对象身份及多参数形式。@return 实际事实。"""
    output = []
    debugger = IceCreamDebugger(outputFunction=output.append, noColor=True)
    value = {'n': 1}
    single = debugger(value)
    multiple = debugger(value, 0)
    empty = debugger()
    return {'debugger_passes_values_through_without_copying': single is value
        and isinstance(multiple, tuple) and multiple[0] is value and multiple[1] == 0
        and empty is None and len(output) == 3}


def disabled() -> dict:
    """核Python求值先于已禁用调试器的调用。@return 实际事实。"""
    output, effects = [], []
    debugger = IceCreamDebugger(outputFunction=output.append, noColor=True)
    debugger.disable()

    def costly():
        """记录合成副作用。@return 合成值。"""
        effects.append('called')
        return 7

    result = debugger(costly())
    return {'disabled_debugger_suppresses_output_but_not_argument_evaluation':
        result == 7 and effects == ['called'] and output == []}


def formatting() -> dict:
    """核format返回文本且不受输出开关控制。@return 实际事实。"""
    output = []
    debugger = IceCreamDebugger(prefix='trace| ', outputFunction=output.append, noColor=True)
    debugger.disable()
    value = 5
    text = debugger.format(value)
    return {'format_returns_text_without_emitting_even_when_disabled':
        isinstance(text, str) and text.startswith('trace| ') and 'value: 5' in text and output == []}


def formatting_limits() -> dict:
    """核值格式器不能消除表达式源码中的业务字面。@return 实际事实。"""
    output = []
    debugger = IceCreamDebugger(outputFunction=output.append, noColor=True,
        argToStringFunction=lambda value: '<redacted>')
    payload = {'token': 'synthetic-token'}
    debugger(payload)
    debugger(str('synthetic-token'))
    return {'value_formatter_does_not_redact_expression_source': len(output) == 2
        and '<redacted>' in output[0] and 'synthetic-token' not in output[0]
        and '<redacted>' in output[1] and 'synthetic-token' in output[1]}


def configuration_ownership() -> dict:
    """核动态前缀每次求值以及独立实例配置。@return 实际事实。"""
    first_output, second_output, prefix_calls = [], [], []

    def prefix():
        """构造合成调用身份。@return 当前前缀。"""
        prefix_calls.append(1)
        return 'A' + str(len(prefix_calls)) + '| '

    first = IceCreamDebugger(prefix=prefix, outputFunction=first_output.append, noColor=True)
    second = IceCreamDebugger(prefix='B| ', outputFunction=second_output.append, noColor=True)
    first(1)
    first(2)
    second(3)
    first.configureOutput(prefix='A-fixed| ')
    first(4)
    second(5)
    return {'callable_prefix_is_per_emission_and_instances_keep_configuration': len(prefix_calls) == 2
        and [line.split('|')[0] for line in first_output] == ['A1', 'A2', 'A-fixed']
        and len(second_output) == 2 and all(line.startswith('B| ') for line in second_output)}


def main() -> None:
    """用类定义的实际文件核候选，避免包导出覆盖__file__造成误判。@return None。"""
    entries = {'IC-U01': (passthrough, 'debugger_passes_values_through_without_copying'),
        'IC-C01': (disabled, 'disabled_debugger_suppresses_output_but_not_argument_evaluation'),
        'IC-U02': (formatting, 'format_returns_text_without_emitting_even_when_disabled'),
        'IC-C02': (formatting_limits, 'value_formatter_does_not_redact_expression_source'),
        'IC-P01': (configuration_ownership, 'callable_prefix_is_per_emission_and_instances_keep_configuration')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(getfile(IceCreamDebugger)).resolve() == root / 'library/icecream/icecream.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
