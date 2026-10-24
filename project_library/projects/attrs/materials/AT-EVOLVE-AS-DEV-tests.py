"""公开跨模型演化回归。"""
import attrs
import pytest
from attrs.evolution import evolve_as

def test_base_order_evolves_into_shipping_order():
    @attrs.define
    class Base:
        number: int
    @attrs.define
    class Shipping(Base):
        tracking: str = 'pending'
    source = Base(7)
    target = evolve_as(source, Shipping, tracking='sent')
    assert isinstance(target, Shipping) and target.number == 7 and target.tracking == 'sent'

def test_source_names_map_to_target_initialization_aliases():
    @attrs.define
    class Source:
        _quantity: int = attrs.field(alias='source_qty')
    @attrs.define
    class Target:
        _quantity: int = attrs.field(alias='target_qty')
    assert evolve_as(Source(source_qty=3), Target, target_qty=5)._quantity == 5

def test_target_converters_and_validators_run():
    @attrs.define
    class Source:
        quantity: str
    @attrs.define
    class Target:
        quantity: int = attrs.field(converter=int, validator=attrs.validators.ge(0))
    assert evolve_as(Source('4'), Target).quantity == 4
    with pytest.raises(ValueError):
        evolve_as(Source('-1'), Target)

def test_init_false_state_is_not_copied():
    @attrs.define
    class Source:
        value: int
        internal: str = attrs.field(init=False, default='source')
    @attrs.define
    class Target:
        value: int
        internal: str = attrs.field(init=False, default='target')
    assert evolve_as(Source(1), Target).internal == 'target'

def test_required_target_fields_and_unknown_aliases_are_explicit():
    @attrs.define
    class Source:
        value: int
    @attrs.define
    class Target:
        value: int
        required: str
    with pytest.raises(TypeError):
        evolve_as(Source(1), Target)
    with pytest.raises(TypeError):
        evolve_as(Source(1), Source, unknown=3)

def test_source_and_regular_evolve_are_preserved():
    @attrs.define
    class Source:
        value: int
    original = Source(1)
    assert evolve_as(original, Source, value=2).value == 2 and original.value == 1
    assert attrs.evolve(original, value=3).value == 3
