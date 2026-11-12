"Public regression tests for CF-SNAPSHOT-DEV; the complete business contract is in materials/CF-SNAPSHOT-DEV-contract.md."
import pytest
from confuse import RootView,ConfigSource,ConfigValueError,Sequence

def test_nested_precedence_and_detachment():
    high=ConfigSource({'db':{'host':'top'}});low=ConfigSource({'db':{'host':'base','port':8}})
    view=RootView([high,low]);result=view.snapshot();high['db']['host']='later'
    assert dict(result['db'])=={'host':'top','port':8}
    with pytest.raises(TypeError): result['db']['host']='bad'

def test_list_redaction_and_subview_relative_paths():
    view=RootView([ConfigSource({'users':[{'name':'a','token':'secret'}]})]);view['users'][0]['token'].redact=True
    result=view['users'].snapshot(redact=True)
    assert result[0]['token']=='REDACTED' and result[0]['name']=='a'
    assert view['users'].snapshot()[0]['token']=='secret'

def test_template_validation_and_immutable_arrays():
    view=RootView([ConfigSource({'v':[1,2],'bad':'wrong'})]);assert view['v'].snapshot()==(1,2)
    assert view['v'].snapshot(Sequence(int))==(1,2)
    with pytest.raises(ConfigValueError): view['bad'].snapshot(int)

def test_cycles_and_unsupported_mutable_objects_are_rejected():
    value=[];value.append(value);view=RootView([ConfigSource({'v':value,'bad':set([1])})])
    with pytest.raises(ValueError): view['v'].snapshot()
    with pytest.raises(TypeError): view['bad'].snapshot()
