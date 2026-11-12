"Public regression tests for ICECREAM-O04-DEV; the complete business contract is in materials/ICECREAM-O04-DEV-contract.md."
from icecream import IceCreamDebugger
import pytest

def test_invalid_combination_leaves_all_original_fields():
    "Verify invalid combination leaves all original fields."
    output=[];debug=IceCreamDebugger(prefix='old|',outputFunction=output.append);before=vars(debug).copy()
    with pytest.raises(TypeError):debug.configureOutput(prefix='new|',outputFunction=123,noColor=True)
    assert vars(debug)==before
    with pytest.raises(ValueError):debug.configureOutput(prefix='new|',lineWrapWidth=True)
    assert vars(debug)==before

def test_valid_callable_not_evaluated_until_real_output():
    "Verify valid callable not evaluated until real output."
    called=[];output=[];debug=IceCreamDebugger()
    def prefix():called.append(1);return 'dynamic|'
    debug.configureOutput(prefix=prefix,outputFunction=output.append,includeContext=False,lineWrapWidth=100,noColor=True)
    assert called==[];assert debug(7)==7 and called==[1] and output[0].startswith('dynamic|')

def test_constructor_and_absent_noarg_compatibility():
    "Verify constructor and absent noarg compatibility."
    with pytest.raises(TypeError):IceCreamDebugger(argToStringFunction=None)
    with pytest.raises(TypeError):IceCreamDebugger(includeContext=1)
    debug=IceCreamDebugger(prefix='')
    with pytest.raises(TypeError):debug.configureOutput()
    with pytest.raises(TypeError):debug.configureOutput(unknown=True)
