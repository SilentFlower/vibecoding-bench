"""dataclass默认工厂不可充当唯一必需联合判别字段。"""
from dataclasses import dataclass, field
from typing import Literal
import pytest
from cattrs import Converter

def test_default_factory_is_not_required_discriminator():
    """两种真正歧义的记录必须拒绝而非猜测。@return None。"""
    @dataclass
    class One:
        """只含共同字段。"""
        x: int
    @dataclass
    class Two:
        """额外字段有默认工厂。"""
        x: int
        labels: list = field(default_factory=list)
    for target in (One | Two, Two | One):
        with pytest.raises(TypeError): Converter().structure({'x': 1}, target)

def test_real_required_discriminator():
    """真正必需的独有字段仍可判别。@return None。"""
    @dataclass
    class One:
        """第一条目。"""
        x: int
        name: str
    @dataclass
    class Two:
        """第二条目。"""
        x: int
        code: int
    assert isinstance(Converter().structure({'x': 1, 'name': 'a'}, One | Two), One)

def test_literal_discriminator_still_works():
    """Literal优先判别和工厂默认共存。@return None。"""
    @dataclass
    class One:
        """第一标签。"""
        kind: Literal['one']
        labels: list = field(default_factory=list)
    @dataclass
    class Two:
        """第二标签。"""
        kind: Literal['two']
    assert isinstance(Converter().structure({'kind': 'one'}, One | Two), One)
