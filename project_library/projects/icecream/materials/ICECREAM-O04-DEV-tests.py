"""配置验证先于任何字段和内置输出器自动切换。"""
from icecream import IceCreamDebugger
import pytest

def test_invalid_combination_leaves_all_original_fields():
    """prefix先变而callback无效的半配置不能残留。@return None。"""
    output=[];debug=IceCreamDebugger(prefix='old|',outputFunction=output.append);before=vars(debug).copy()
    with pytest.raises(TypeError):debug.configureOutput(prefix='new|',outputFunction=123,noColor=True)
    assert vars(debug)==before
    with pytest.raises(ValueError):debug.configureOutput(prefix='new|',lineWrapWidth=True)
    assert vars(debug)==before

def test_valid_callable_not_evaluated_until_real_output():
    """验证不执行prefix回调，合法整组配置一次生效。@return None。"""
    called=[];output=[];debug=IceCreamDebugger()
    def prefix():called.append(1);return 'dynamic|'
    debug.configureOutput(prefix=prefix,outputFunction=output.append,includeContext=False,lineWrapWidth=100,noColor=True)
    assert called==[];assert debug(7)==7 and called==[1] and output[0].startswith('dynamic|')

def test_constructor_and_absent_noarg_compatibility():
    """构造时同样验证，未传参数及未知参数仍明确拒绝。@return None。"""
    with pytest.raises(TypeError):IceCreamDebugger(argToStringFunction=None)
    with pytest.raises(TypeError):IceCreamDebugger(includeContext=1)
    debug=IceCreamDebugger(prefix='')
    with pytest.raises(TypeError):debug.configureOutput()
    with pytest.raises(TypeError):debug.configureOutput(unknown=True)
