"""同一API可接单条记录或一组记录，仍走真实嵌套钩子。"""
from dataclasses import dataclass
from collections.abc import Sequence
import pytest
from cattrs import Converter

@dataclass
class Product:
    """真实产品记录。"""
    quantity: int

def test_mapping_and_sequence():
    """字典结构成单条，列表结构成序列。@return None。"""
    from cattrs.strategies.sequence_union import configure_sequence_union
    target = Sequence[Product] | Product
    converter = configure_sequence_union(Converter(), target)
    assert converter.structure({'quantity': '2'}, target) == Product(2)
    assert list(converter.structure([{'quantity': '3'}], target)) == [Product(3)]

def test_empty_tuple_and_nested_hook():
    """空序列及tuple可用，元素继续应用用户钩子。@return None。"""
    from cattrs.strategies.sequence_union import configure_sequence_union
    target = list[Product] | Product
    converter = Converter()
    converter.register_structure_hook(int, lambda value, target: int(value) + 10)
    configure_sequence_union(converter, target)
    assert converter.structure([], target) == []
    assert converter.structure(({'quantity': '1'},), target) == [Product(11)]

def test_text_and_ambiguous_rejected():
    """文本不当业务序列，多个序列分支拒绝。@return None。"""
    from cattrs.strategies.sequence_union import configure_sequence_union
    converter = configure_sequence_union(Converter(), list[Product] | Product)
    with pytest.raises(TypeError): converter.structure('not a record', list[Product] | Product)
    with pytest.raises(TypeError): configure_sequence_union(Converter(), list[int] | tuple[int, ...])
