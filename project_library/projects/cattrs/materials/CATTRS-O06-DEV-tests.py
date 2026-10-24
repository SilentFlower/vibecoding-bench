"Public regression tests for CATTRS-O06-DEV; the complete business contract is in materials/CATTRS-O06-DEV-contract.md."
from dataclasses import dataclass
from collections.abc import Sequence
import pytest
from cattrs import Converter

@dataclass
class Product:
    "Public regression fixture: Product."
    quantity: int

def test_mapping_and_sequence():
    "Verify mapping and sequence."
    from cattrs.strategies.sequence_union import configure_sequence_union
    target = Sequence[Product] | Product
    converter = configure_sequence_union(Converter(), target)
    assert converter.structure({'quantity': '2'}, target) == Product(2)
    assert list(converter.structure([{'quantity': '3'}], target)) == [Product(3)]

def test_empty_tuple_and_nested_hook():
    "Verify empty tuple and nested hook."
    from cattrs.strategies.sequence_union import configure_sequence_union
    target = list[Product] | Product
    converter = Converter()
    converter.register_structure_hook(int, lambda value, target: int(value) + 10)
    configure_sequence_union(converter, target)
    assert converter.structure([], target) == []
    assert converter.structure(({'quantity': '1'},), target) == [Product(11)]

def test_text_and_ambiguous_rejected():
    "Verify text and ambiguous rejected."
    from cattrs.strategies.sequence_union import configure_sequence_union
    converter = configure_sequence_union(Converter(), list[Product] | Product)
    with pytest.raises(TypeError): converter.structure('not a record', list[Product] | Product)
    with pytest.raises(TypeError): configure_sequence_union(Converter(), list[int] | tuple[int, ...])
