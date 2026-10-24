"""无长度可重读数据源应单次扫描判重。"""
import pytest
from toolz import isdistinct


class Reiterable:
    """不提供长度的可重复业务查询。"""
    def __init__(self, values):
        """保存数据。@param values 数据。@return None。"""
        self.values = values
        self.reads = 0
    def __iter__(self):
        """每次只返回一个流。@return 迭代器。"""
        self.reads += 1
        return iter(self.values)


def test_reiterable_unique_and_duplicate():
    """无长度源支持唯一和重复结果且不重读。@return None。"""
    for values, expected in [([1, 2, 3], True), ([1, 2, 1], False), ([], True)]:
        source = Reiterable(values)
        assert isdistinct(source) is expected
        assert source.reads == 1


def test_short_circuit():
    """发现首个重复后不访问故障尾部。@return None。"""
    class Stream:
        """包含不可达故障尾部的数据源。"""
        def __iter__(self):
            """产生两个重复值。@return 迭代器。"""
            yield 1
            yield 1
            raise RuntimeError('must not read')
    assert isdistinct(Stream()) is False


def test_real_length_error_propagates():
    """真实长度实现错误不被当作缺少长度。@return None。"""
    class Broken(Reiterable):
        """具有故障长度函数的数据源。"""
        def __len__(self):
            """失败。@return 不返回。"""
            raise TypeError('length body')
    with pytest.raises(TypeError, match='length body'):
        isdistinct(Broken([1]))
