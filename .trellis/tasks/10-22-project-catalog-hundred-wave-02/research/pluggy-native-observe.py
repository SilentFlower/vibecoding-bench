"""在实际候选中核钩子顺序、默认参数、子集和历史事件所有权。"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pluggy
from pluggy import HookimplMarker, HookspecMarker, PluginManager, PluginValidationError


SPEC = HookspecMarker('warehouse')
IMPL = HookimplMarker('warehouse')


class RenderSpec:
    """库存渲染的最小可信协议。"""
    @SPEC
    def render(self, value):
        """渲染合成库存值。@param value 值。@return 可选结果。"""


class NamedPlugin:
    """提供可独立注册的普通插件。"""
    def __init__(self, name):
        """保存合成前缀。@param name 名称。@return None。"""
        self.name = name

    @IMPL
    def render(self, value):
        """生成独立结果。@param value 值。@return 文本。"""
        return self.name + ':' + value


def main() -> None:
    """执行单条合成控制，不发现或加载宿主入口点。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(pluggy.__file__).resolve() == root / 'library/src/pluggy/__init__.py'}
    task = sys.argv[1]
    manager = PluginManager('warehouse')
    if task == 'PG-U01':
        manager.add_hookspecs(RenderSpec)
        class First:
            """显式前置实现。"""
            @IMPL(tryfirst=True)
            def render(self, value):
                """返回前置结果。@param value 值。@return 文本。"""
                return 'first:' + value
        class Last:
            """显式后置且不产出结果的实现。"""
            @IMPL(trylast=True)
            def render(self, value):
                """只记录已调用。@param value 值。@return None。"""
                events.append('last:' + value)
        events = []
        for name, plugin in [('A', NamedPlugin('A')), ('first', First()), ('B', NamedPlugin('B')), ('last', Last())]:
            manager.register(plugin, name)
        result['ordinary_hooks_use_declared_priority_and_drop_only_none_results'] = (
            manager.hook.render(value='X') == ['first:X', 'B:X', 'A:X'] and events == ['last:X'])
    elif task == 'PG-C01':
        class Choose:
            """第一个非None结果的协议。"""
            @SPEC(firstresult=True)
            def select(self, value):
                """选择本地值。@param value 值。@return 单个结果。"""
        manager.add_hookspecs(Choose)
        events = []
        class Fallback:
            """没有结果时才使用的后备。"""
            @IMPL(trylast=True)
            def select(self, value):
                """记录后备调用。@param value 值。@return 文本。"""
                events.append('fallback')
                return 'FALLBACK'
        class Primary:
            """返回合法假值的实现。"""
            @IMPL
            def select(self, value):
                """保留原值。@param value 值。@return 输入值。"""
                return value
        manager.register(Fallback(), 'fallback')
        manager.register(Primary(), 'primary')
        false_value = manager.hook.select(value=False)
        zero_value = manager.hook.select(value=0)
        empty = manager.hook.select(value=None)
        result['firstresult_stops_on_false_and_zero_but_not_none'] = false_value is False and type(zero_value) is int and zero_value == 0 and empty == 'FALLBACK' and events == ['fallback']
    elif task == 'PG-U02':
        class Defaults:
            """协议声明默认前缀。"""
            @SPEC
            def render(self, value, prefix='APP'):
                """提供兼容的默认参数。@param value 值。@param prefix 前缀。@return 文本。"""
        class Full:
            """实现自身默认不覆盖协议默认。"""
            @IMPL
            def render(self, value, prefix='PLUGIN'):
                """渲染实际收到的参数。@param value 值。@param prefix 前缀。@return 文本。"""
                return prefix + ':' + value
        manager.add_hookspecs(Defaults)
        manager.register(Full(), 'full')
        manager.register(NamedPlugin('short'), 'short')
        result['spec_defaults_and_argument_pruning_support_compatible_implementations'] = (
            manager.hook.render(value='X') == ['short:X', 'APP:X']
            and manager.hook.render(value='X', prefix='EXPLICIT') == ['short:X', 'EXPLICIT:X'])
    elif task == 'PG-C02':
        class Unknown:
            """普通未知实现。"""
            @IMPL
            def absent(self):
                """声明未定义协议。@return None。"""
        class Optional:
            """明确允许缺少协议的实现。"""
            @IMPL(optionalhook=True)
            def absent(self):
                """声明可选协议。@return None。"""
        first = manager.register(Unknown(), 'unknown')
        rejected = False
        try:
            manager.check_pending()
        except PluginValidationError:
            rejected = True
        other = PluginManager('warehouse')
        other.register(Optional(), 'optional')
        other.check_pending()
        result['unknown_hook_validation_is_explicit_and_optional_is_deliberate'] = first == 'unknown' and rejected
    elif task == 'PG-U03':
        manager.add_hookspecs(RenderSpec)
        first, second = NamedPlugin('A'), NamedPlugin('B')
        manager.register(first, 'A')
        manager.register(second, 'B')
        selected = manager.subset_hook_caller('render', remove_plugins=[second])
        result['subset_call_does_not_unregister_or_mutate_the_full_hook'] = (
            selected(value='X') == ['A:X'] and manager.hook.render(value='X') == ['B:X', 'A:X']
            and manager.get_plugin('B') is second)
    elif task == 'PG-P01':
        class History:
            """为后注册插件重放事件。"""
            @SPEC(historic=True)
            def event(self, payload):
                """接收合成快照。@param payload 值。@return None。"""
        class Recorder:
            """只保留收到的合成字符串。"""
            def __init__(self):
                """创建独立记录。@return None。"""
                self.values = []
            @IMPL
            def event(self, payload):
                """记录事件值。@param payload 载荷。@return None。"""
                self.values.append(payload['sku'])
        manager.add_hookspecs(History)
        original = {'payload': {'sku': 'A'}}
        manager.hook.event.call_historic(kwargs=original)
        original['payload']['sku'] = 'B'
        late = Recorder()
        manager.register(late, 'late')
        owned = PluginManager('warehouse')
        owned.add_hookspecs(History)
        original = {'payload': {'sku': 'A'}}
        owned.hook.event.call_historic(kwargs=deepcopy(original))
        original['payload']['sku'] = 'B'
        control = Recorder()
        owned.register(control, 'late')
        result['historic_replay_needs_owned_snapshot_for_mutable_event_payloads'] = late.values == ['B'] and control.values == ['A']
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
