"""严格策略必须影响真实嵌套结构而非只包一层示例。"""
from dataclasses import dataclass
import pytest
from cattrs import Converter

def test_exact_primitives():
    """字符串整数与bool整数不能误通过。@return None。"""
    from cattrs.strategies.strict import configure_strict_primitives
    converter = configure_strict_primitives(Converter())
    for value in ('2', True):
        with pytest.raises(TypeError): converter.structure(value, int)
    assert converter.structure(2, int) == 2 and converter.structure(False, bool) is False
    assert Converter().structure('2', int) == 2

def test_nested_path_and_float_policy():
    """嵌套字段错误保持框架路径，浮点扩展明确。@return None。"""
    from cattrs.strategies.strict import configure_strict_primitives
    from cattrs.v import transform_error
    @dataclass
    class Record:
        """库存记录。"""
        quantity: int
    converter = configure_strict_primitives(Converter())
    with pytest.raises(Exception) as result: converter.structure({'quantity': '3'}, Record)
    assert 'quantity' in str(transform_error(result.value))
    assert configure_strict_primitives(Converter(), allow_int_float=True).structure(3, float) == 3.0

def test_nonfinite_and_subclass():
    """非有限浮点和非精确子类的政策可证伪。@return None。"""
    from cattrs.strategies.strict import configure_strict_primitives
    converter = configure_strict_primitives(Converter())
    with pytest.raises(ValueError): converter.structure(float('nan'), float)
    class Text(str):
        """自定义文本子类。"""
    with pytest.raises(TypeError): converter.structure(Text('x'), str)
