"""逐条校验保留编号和错误政策，不读取超出上限的输入。"""
from cerberus import Validator

def test_lazy_continue_and_independent_results():
    """首条提前取得，失败后继续且各条状态独立。@return None。"""
    from cerberus.stream import iter_validated
    seen = []
    def records():
        """实际一次性流。@return 迭代器。"""
        for value in [1, 'bad', 3]:
            seen.append(value)
            yield {'x': value}
    stream = iter_validated(records(), {'x': {'type': 'integer'}})
    first = next(stream)
    assert first['index'] == 1 and first['result'].valid and seen == [1]
    rest = list(stream)
    assert [row['result'].valid for row in rest] == [False, True]
    assert first['result'].document == {'x': 1}

def test_stop_raise_and_nondocument():
    """错误政策显式，非映射记录也可继续。@return None。"""
    import pytest
    from cerberus.stream import iter_validated, ValidationStreamError
    assert len(list(iter_validated([{}, 4, {}], {}, on_error='stop'))) == 2
    with pytest.raises(ValidationStreamError) as result:
        list(iter_validated([4], {}, on_error='raise'))
    assert result.value.index == 1 and not result.value.result.valid

def test_exact_limit_and_zero():
    """消费上限不额外读取下一条，零不触发流。@return None。"""
    from cerberus.stream import iter_validated
    source = iter([{'x': 1}, {'x': 2}])
    assert len(list(iter_validated(source, {}, max_records=1, validator_options={'allow_unknown': True}))) == 1
    assert next(source) == {'x': 2}
    assert list(iter_validated(iter([4]), {}, max_records=0)) == []
