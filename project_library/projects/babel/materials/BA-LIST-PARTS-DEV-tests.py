"""公开列表分段交付回归。"""
import pytest
from babel.lists import format_list, format_list_to_parts

def test_concatenation_matches_localized_lists():
    for locale in ('en', 'zh', 'fr', 'fi'):
        for count in range(5):
            values = ['a', 'b', 'c', 'd'][:count]
            assert ''.join(p['value'] for p in format_list_to_parts(values, locale=locale)) == format_list(values, locale=locale)

def test_repeated_empty_and_braced_elements_keep_original_indices():
    values = ['', '{0}', '{0}', '雪']
    parts = format_list_to_parts(values, locale='en')
    assert [(p['index'], p['value']) for p in parts if p['type'] == 'element'] == list(enumerate(values))
    assert all(p['index'] is None for p in parts if p['type'] == 'literal')

def test_style_fallback_matches_existing_formatter():
    values = ['one', 'two', 'three']
    for style in ('or', 'unit-short', 'standard-narrow'):
        assert ''.join(p['value'] for p in format_list_to_parts(values, style, 'en')) == format_list(values, style, 'en')

def test_input_is_unchanged_and_non_text_is_rejected():
    values = ['a', 'b']
    format_list_to_parts(values, locale='en')
    assert values == ['a', 'b']
    with pytest.raises(TypeError):
        format_list_to_parts(['a', 1], locale='en')
