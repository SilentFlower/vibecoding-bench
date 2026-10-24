"Public regression tests for DC-CSV-DEV; the complete business contract is in materials/DC-CSV-DEV-contract.md."
import pytest
from decouple import Csv


def test_csv_literal_fields():
    "Verify csv literal fields."
    assert Csv(mode='csv')(r'\d+,x#y,,z,') == [r'\d+', 'x#y', '', 'z', '']


def test_csv_quotes_and_casts():
    "Verify csv quotes and casts."
    assert Csv(mode='csv', post_process=tuple)('"a,b","say ""hi"""') == ('a,b', 'say "hi"')
    assert Csv(int, mode='csv')('1,2,3') == [1, 2, 3]


def test_invalid_csv_and_legacy():
    "Verify invalid csv and legacy."
    with pytest.raises(ValueError):
        Csv(mode='csv')('"unterminated')
    with pytest.raises(ValueError):
        Csv(mode='csv', delimiter=',;')
    assert Csv()("a,'b,c'") == ['a', 'b,c']
    assert Csv(mode='csv')(None) == []
