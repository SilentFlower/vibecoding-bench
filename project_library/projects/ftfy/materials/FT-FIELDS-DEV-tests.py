"Public regression tests for FT-FIELDS-DEV; the complete business contract is in materials/FT-FIELDS-DEV-contract.md."
import pytest
from ftfy import TextFixerConfig
from ftfy.structured import fix_fields

def test_selected_nested_values_only_and_input_is_detached():
    value={'users':[{'name':'cafÃ©','raw':'cafÃ©'}]};result=fix_fields(value,[('users',0,'name')])
    assert result=={'users':[{'name':'café','raw':'cafÃ©'}]} and value['users'][0]['name']=='cafÃ©'

def test_dotted_keys_none_and_missing_policy_are_explicit():
    value={'a.b':'cafÃ©','none':None}
    assert fix_fields(value,[('a.b',),('none',),('missing',)],missing='skip')=={'a.b':'café','none':None}

def test_later_bad_field_never_changes_original():
    value={'name':'cafÃ©','bad':7}
    with pytest.raises(TypeError): fix_fields(value,[('name',),('bad',)])
    assert value=={'name':'cafÃ©','bad':7}

def test_root_text_and_caller_policy_are_supported():
    assert fix_fields('ﬁ',[()],TextFixerConfig(fix_latin_ligatures=False))=='ﬁ'
    with pytest.raises(ValueError): fix_fields({},[('x',-1)])
