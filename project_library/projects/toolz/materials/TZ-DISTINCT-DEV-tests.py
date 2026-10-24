"Public regression tests for TZ-DISTINCT-DEV; the complete business contract is in materials/TZ-DISTINCT-DEV-contract.md."
import pytest
from toolz import isdistinct


class Reiterable:
    "Public regression fixture: Reiterable."
    def __init__(self, values):
        "Support the public regression through __init__."
        self.values = values
        self.reads = 0
    def __iter__(self):
        "Support the public regression through __iter__."
        self.reads += 1
        return iter(self.values)


def test_reiterable_unique_and_duplicate():
    "Verify reiterable unique and duplicate."
    for values, expected in [([1, 2, 3], True), ([1, 2, 1], False), ([], True)]:
        source = Reiterable(values)
        assert isdistinct(source) is expected
        assert source.reads == 1


def test_short_circuit():
    "Verify short circuit."
    class Stream:
        "Public regression fixture: Stream."
        def __iter__(self):
            "Support the public regression through __iter__."
            yield 1
            yield 1
            raise RuntimeError('must not read')
    assert isdistinct(Stream()) is False


def test_real_length_error_propagates():
    "Verify real length error propagates."
    class Broken(Reiterable):
        "Public regression fixture: Broken."
        def __len__(self):
            "Support the public regression through __len__."
            raise TypeError('length body')
    with pytest.raises(TypeError, match='length body'):
        isdistinct(Broken([1]))
