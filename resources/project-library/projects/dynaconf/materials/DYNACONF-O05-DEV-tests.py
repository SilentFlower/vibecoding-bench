"Public regression tests for DYNACONF-O05-DEV; the complete business contract is in materials/DYNACONF-O05-DEV-contract.md."
from dynaconf import Dynaconf
import pytest

def test_json_profile_parses_null_and_arrays_while_default_instance_stays_toml():
    "Verify json profile parses null and arrays while default instance stays toml."
    custom=Dynaconf(environments=False);original=Dynaconf(environments=False);custom.set_value_parser('json')
    custom.set('VALUE','null',tomlfy=True);original.set('VALUE','null',tomlfy=True)
    assert custom.VALUE is None and original.VALUE=='null'
    custom.set('ITEMS','[true, null, 2]',tomlfy=True);assert custom.ITEMS==[True,None,2]

def test_explicit_tokens_and_real_environment_loader_keep_priority(monkeypatch):
    "Verify explicit tokens and real environment loader keep priority."
    from dynaconf.loaders import env_loader
    settings=Dynaconf(environments=False,envvar_prefix='PROBE');settings.set_value_parser('json')
    settings.set('TEXT','@str null',tomlfy=True);settings.set('NUMBER','@int 3',tomlfy=True)
    assert settings.TEXT=='null' and settings.NUMBER==3
    monkeypatch.setenv('PROBE_VALUE','null');env_loader.load(settings)
    assert settings.VALUE is None

def test_literal_callable_error_policies_none_and_programming_errors_are_explicit():
    "Verify literal callable error policies none and programming errors are explicit."
    settings=Dynaconf(environments=False);settings.set_value_parser('literal');settings.set('VALUE',"('a', 1)",tomlfy=True)
    assert settings.VALUE==('a',1) or settings.VALUE==['a',1]
    settings.set_value_parser('json',errors='string');settings.set('VALUE','plain',tomlfy=True);assert settings.VALUE=='plain'
    settings.set_value_parser('json')
    with pytest.raises(ValueError):settings.set('VALUE','plain',tomlfy=True)
    def broken(value):raise RuntimeError('programming error')
    settings.set_value_parser(broken,errors='string')
    with pytest.raises(RuntimeError):settings.set('VALUE','x',tomlfy=True)
    settings.set_value_parser(None);settings.set('VALUE','true',tomlfy=True);assert settings.VALUE is True
