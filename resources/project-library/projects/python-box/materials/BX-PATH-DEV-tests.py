"Public regression tests for BX-PATH-DEV; the complete business contract is in materials/BX-PATH-DEV-contract.md."
import pytest
from box import Box, BoxError


def test_literal_segments():
    "Verify literal segments."
    value = Box({'a.b': {'2': 'text', 2: 'integer'}, 'rows': [{'n': 1}]})
    assert value.get_path(['a.b', 2]) == 'integer'
    assert value.get_path(['a.b', '2']) == 'text'
    assert value.get_path(['rows', -1, 'n']) == 1


def test_assignment_and_delete():
    "Verify assignment and delete."
    value = Box({'node': {}}, box_dots=True, default_box=True)
    value.set_path(['node', 'a.b'], {'x': 2})
    assert value.get_path(['node', 'a.b', 'x']) == 2
    value.delete_path(['node', 'a.b'])
    assert value.get_path(['node', 'a.b'], None) is None


def test_missing_no_default_creation_and_frozen():
    "Verify missing no default creation and frozen."
    value = Box(default_box=True)
    assert value.get_path(['missing'], None) is None and value.to_dict() == {}
    with pytest.raises(ValueError):
        value.get_path([])
    with pytest.raises(BoxError):
        Box({'a': 1}, frozen_box=True).set_path(['a'], 2)
