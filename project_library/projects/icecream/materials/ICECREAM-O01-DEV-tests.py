"""展开实参值不能丢失或重新求值，安全普通前后缀仍可标注。"""
from icecream import IceCreamDebugger

def test_single_star_with_prefix_suffix_and_identity():
    """展开加尾参保留全部值及返回身份。@return None。"""
    output=[];debug=IceCreamDebugger(outputFunction=output.append);values=[101,202]
    result=debug(9,*values,303)
    assert result==(9,101,202,303) and all(str(value) in output[0] for value in result)
    assert 'expanded[0]' in output[0] and 'expanded[1]' in output[0]

def test_multiple_empty_stars_and_generator_consumed_once():
    """多个展开间普通值不能误认来源，生成器不被二次消费。@return None。"""
    output=[];debug=IceCreamDebugger(outputFunction=output.append);visited=[]
    def values():
        for value in [11,22]:visited.append(value);yield value
    result=debug(*values(),33,*[],44)
    assert result==(11,22,33,44) and visited==[11,22]
    assert all(str(value) in output[-1] for value in result)
    assert debug(*[],55)==55 and '55' in output[-1]

def test_no_source_and_single_object_identity():
    """源码不可用沿原fallback，单个对象身份保持。@return None。"""
    import warnings
    output=[];debug=IceCreamDebugger(outputFunction=output.append);obj=object()
    assert debug(obj) is obj
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');exec('debug(*[77,88],99)',{'debug':debug})
    assert all(str(value) in output[-1] for value in [77,88,99])
