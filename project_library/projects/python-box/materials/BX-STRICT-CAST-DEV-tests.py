"Public regression tests for BX-STRICT-CAST-DEV; the complete business contract is in materials/BX-STRICT-CAST-DEV-contract.md."
import pytest
from box import ConfigBox


def test_strict_boolean_and_default_none():
    "Verify strict boolean and default none."
    value = ConfigBox(known=' YES ', unknown='maybe', zero='0')
    assert value.bool('known', strict=True) is True
    assert value.bool('zero', strict=True) is False
    with pytest.raises(ValueError):
        value.bool('unknown', strict=True)
    assert value.bool('missing', default=None, strict=True) is None
    assert value.bool('unknown') is True


def test_strict_numeric_boundaries():
    "Verify strict numeric boundaries."
    value = ConfigBox(port='8080', flag=True, nan='nan', inf='inf')
    assert value.int('port', strict=True) == 8080
    with pytest.raises(ValueError):
        value.int('flag', strict=True)
    for key in ('nan', 'inf'):
        with pytest.raises(ValueError):
            value.float(key, strict=True)


def test_strict_list_and_safe_error():
    "Verify strict list and safe error."
    value = ConfigBox(rows='1,2,3', secret='private-secret')
    assert value.list('rows', mod=int, strict=True) == [1, 2, 3]
    with pytest.raises(ValueError) as result:
        value.int('secret', strict=True)
    assert 'private-secret' not in str(result.value)
