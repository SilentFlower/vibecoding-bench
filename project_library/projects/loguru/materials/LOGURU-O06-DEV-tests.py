"""实际占位才计算惰性参数，每事件缓存而非每sink重复计算。"""
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    """创建独立logger。@return Logger。"""
    logger.remove();log=deepcopy(logger);log.remove();return log

def test_mixed_values_unused_and_repeated_placeholders_evaluate_once():
    """普通参数可混用，未引用参数不算，同一个包装器的不同位置仍一次。@return None。"""
    from loguru import LazyValue
    calls=[];log=clean();a=[];b=[];log.add(a.append,format='{message}');log.add(b.append,format='{message}')
    used=LazyValue(lambda:calls.append('used') or 12.345);unused=LazyValue(lambda:calls.append('unused') or 'never')
    log.info('{name} {v:.2f}/{v!r}/{other}',name='Ada',v=used,other=used,unused=unused)
    assert calls==['used'] and ''.join(a)==''.join(b)=='Ada 12.35/12.345/12.345\n'
    log.info('{v}',v=used);assert calls==['used','used'];log.remove()

def test_filtered_arguments_and_serialized_extra_do_not_force_unused_values():
    """低于全局级别直接短路，JSON明确标记未求值而不触发计算。@return None。"""
    import json
    from loguru import LazyValue
    log=clean();out=[];calls=[];log.add(out.append,level='INFO',serialize=True,format='{message}')
    value=LazyValue(lambda:calls.append('computed') or 9)
    log.debug('{v}',v=value);log.info('plain',unused=value)
    assert calls==[] and json.loads(out[0])['record']['extra']['unused']=='<unevaluated LazyValue>'
    log.remove()

def test_conversion_index_attributes_colors_errors_and_legacy_lazy():
    """标准访问及颜色格式使用真实值，异常传播且旧全callable模式保留。@return None。"""
    from loguru import LazyValue
    log=clean();out=[];log.add(out.append,format='{message}',colorize=False,catch=False)
    log.opt(colors=True).info('<red>{item[x]:03d}</red> {text!s}',item=LazyValue(lambda:{'x':7}),text=LazyValue(lambda:'ok'))
    log.opt(lazy=True).info('{}',lambda:'legacy')
    assert ''.join(out)=='007 ok\nlegacy\n'
    def broken():raise RuntimeError('computation failed')
    with pytest.raises(RuntimeError,match='computation failed'):log.info('{x}',x=LazyValue(broken))
    with pytest.raises(TypeError):LazyValue(42)
    log.remove()
