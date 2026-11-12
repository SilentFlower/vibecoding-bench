"Public regression tests for DP-EXACT-DEV; the complete business contract is in materials/DP-EXACT-DEV-contract.md."
from collections import defaultdict
import pytest
from dpath.exact import get_exact

def test_glob_characters_separators_and_typed_keys_are_literal():
    data={'a/b':{'*':{1:'integer','1':'string'}}}
    assert get_exact(data,['a/b','*',1])=='integer' and get_exact(data,['a/b','*','1'])=='string'

def test_empty_path_and_return_identity_are_preserved():
    value=[];data={'a':value}
    assert get_exact(data,()) is data and get_exact(data,iter(['a'])) is value

def test_missing_defaults_and_invalid_list_indices_are_distinct():
    assert get_exact({'a':[1]},['a',2],None) is None
    with pytest.raises(TypeError):
        get_exact({'a':[1]},['a',True])
    with pytest.raises(TypeError):
        get_exact({},'a/b')

def test_read_does_not_create_defaultdict_entries():
    data=defaultdict(list)
    assert get_exact(data,['missing'],'default')=='default' and dict(data)=={}
