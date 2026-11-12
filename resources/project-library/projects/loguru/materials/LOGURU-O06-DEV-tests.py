"Public regression tests for LOGURU-O06-DEV; the complete business contract is in materials/LOGURU-O06-DEV-contract.md."
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    "Support the public regression through clean."
    logger.remove();log=deepcopy(logger);log.remove();return log

def test_mixed_values_unused_and_repeated_placeholders_evaluate_once():
    "Verify mixed values unused and repeated placeholders evaluate once."
    from loguru import LazyValue
    calls=[];log=clean();a=[];b=[];log.add(a.append,format='{message}');log.add(b.append,format='{message}')
    used=LazyValue(lambda:calls.append('used') or 12.345);unused=LazyValue(lambda:calls.append('unused') or 'never')
    log.info('{name} {v:.2f}/{v!r}/{other}',name='Ada',v=used,other=used,unused=unused)
    assert calls==['used'] and ''.join(a)==''.join(b)=='Ada 12.35/12.345/12.345\n'
    log.info('{v}',v=used);assert calls==['used','used'];log.remove()

def test_filtered_arguments_and_serialized_extra_do_not_force_unused_values():
    "Verify filtered arguments and serialized extra do not force unused values."
    import json
    from loguru import LazyValue
    log=clean();out=[];calls=[];log.add(out.append,level='INFO',serialize=True,format='{message}')
    value=LazyValue(lambda:calls.append('computed') or 9)
    log.debug('{v}',v=value);log.info('plain',unused=value)
    assert calls==[] and json.loads(out[0])['record']['extra']['unused']=='<unevaluated LazyValue>'
    log.remove()

def test_conversion_index_attributes_colors_errors_and_legacy_lazy():
    "Verify conversion index attributes colors errors and legacy lazy."
    from loguru import LazyValue
    log=clean();out=[];log.add(out.append,format='{message}',colorize=False,catch=False)
    log.opt(colors=True).info('<red>{item[x]:03d}</red> {text!s}',item=LazyValue(lambda:{'x':7}),text=LazyValue(lambda:'ok'))
    log.opt(lazy=True).info('{}',lambda:'legacy')
    assert ''.join(out)=='007 ok\nlegacy\n'
    def broken():raise RuntimeError('computation failed')
    with pytest.raises(RuntimeError,match='computation failed'):log.info('{x}',x=LazyValue(broken))
    with pytest.raises(TypeError):LazyValue(42)
    log.remove()
