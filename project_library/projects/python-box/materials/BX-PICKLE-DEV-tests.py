"Public regression tests for BX-PICKLE-DEV; the complete business contract is in materials/BX-PICKLE-DEV-contract.md."
import pickle
from box import Box


class ConfigSubclass(Box):
    "Public regression fixture: ConfigSubclass."


def test_nested_subclasses_roundtrip():
    "Verify nested subclasses roundtrip."
    original = ConfigSubclass({'child': {'port': 9}, 'rows': [{'port': 10}]})
    for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
        result = pickle.loads(pickle.dumps(original, protocol=protocol))
        assert type(result) is ConfigSubclass
        assert type(result.child) is ConfigSubclass
        assert type(result.rows[0]) is ConfigSubclass
        assert result == original


def test_frozen_options_and_plain_box():
    "Verify frozen options and plain box."
    original = ConfigSubclass({'child': {'port': 9}}, frozen_box=True, default_box=True)
    result = pickle.loads(pickle.dumps(original))
    assert type(result.child) is ConfigSubclass
    assert result._box_config['frozen_box'] is True
    assert result._box_config['default_box'] is True
    assert pickle.loads(pickle.dumps(Box({'port': 9}))).port == 9


def test_existing_shared_nodes():
    "Verify existing shared nodes."
    original = ConfigSubclass({'child': {'port': 9}})
    dict.__setitem__(original, 'alias', original.child)
    result = pickle.loads(pickle.dumps(original))
    assert result.alias is result.child
