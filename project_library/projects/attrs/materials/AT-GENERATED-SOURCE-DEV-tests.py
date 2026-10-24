"""公开生成源码检查回归。"""
import linecache
import attrs
import pytest
from attrs.introspection import generated_sources

def test_actual_generated_init_and_repr_source_are_available():
    @attrs.define
    class Model:
        value: int = attrs.field(converter=int)
    result = generated_sources(Model, ['__init__','__repr__'])
    assert result['__init__']['generated'] and 'def __init__' in result['__init__']['source']
    assert result['__repr__']['status'] == 'available'

def test_default_names_and_both_mapping_levels_are_readonly():
    @attrs.define
    class Model:
        value: int
    result = generated_sources(Model)
    assert '__init__' in result
    with pytest.raises(TypeError):
        result['x'] = 1
    with pytest.raises(TypeError):
        result['__init__']['source'] = 'fake'

def test_custom_and_missing_methods_are_not_claimed_as_generated():
    @attrs.define
    class Model:
        value: int
        def custom(self):
            raise AssertionError('不得执行')
    result = generated_sources(Model, ['custom','missing'])
    assert result['custom']['status'] == 'custom' and result['custom']['source'] is None
    assert result['missing']['status'] == 'missing'

def test_monkeypatched_method_reports_current_function():
    @attrs.define
    class Model:
        value: int
    def replacement(self):
        return None
    Model.__init__ = replacement
    assert generated_sources(Model, ['__init__'])['__init__']['generated'] is False

def test_missing_linecache_is_reported_without_invented_source():
    @attrs.define
    class Model:
        value: int
    filename = Model.__init__.__code__.co_filename
    saved = linecache.cache.pop(filename, None)
    try:
        assert generated_sources(Model, ['__init__'])['__init__']['status'] == 'unavailable'
    finally:
        if saved is not None:
            linecache.cache[filename] = saved

def test_invalid_method_name_selections_are_rejected():
    @attrs.define
    class Model:
        value: int
    with pytest.raises(TypeError):
        generated_sources(Model, '__init__')
    with pytest.raises(ValueError):
        generated_sources(Model, ['__init__','__init__'])
