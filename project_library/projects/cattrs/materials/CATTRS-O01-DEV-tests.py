"Public regression tests for CATTRS-O01-DEV; the complete business contract is in materials/CATTRS-O01-DEV-contract.md."
from dataclasses import dataclass, field
from typing import Literal
import pytest
from cattrs import Converter

def test_default_factory_is_not_required_discriminator():
    "Verify default factory is not required discriminator."
    @dataclass
    class One:
        "Public regression fixture: One."
        x: int
    @dataclass
    class Two:
        "Public regression fixture: Two."
        x: int
        labels: list = field(default_factory=list)
    for target in (One | Two, Two | One):
        with pytest.raises(TypeError): Converter().structure({'x': 1}, target)

def test_real_required_discriminator():
    "Verify real required discriminator."
    @dataclass
    class One:
        "Public regression fixture: One."
        x: int
        name: str
    @dataclass
    class Two:
        "Public regression fixture: Two."
        x: int
        code: int
    assert isinstance(Converter().structure({'x': 1, 'name': 'a'}, One | Two), One)

def test_literal_discriminator_still_works():
    "Verify literal discriminator still works."
    @dataclass
    class One:
        "Public regression fixture: One."
        kind: Literal['one']
        labels: list = field(default_factory=list)
    @dataclass
    class Two:
        "Public regression fixture: Two."
        kind: Literal['two']
    assert isinstance(Converter().structure({'kind': 'one'}, One | Two), One)
