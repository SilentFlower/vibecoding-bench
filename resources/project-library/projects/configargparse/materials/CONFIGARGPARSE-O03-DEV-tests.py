"Public regression tests for CONFIGARGPARSE-O03-DEV; the complete business contract is in materials/CONFIGARGPARSE-O03-DEV-contract.md."
import json
import configargparse as c

def test_two_parses_do_not_replace_first():
    "Verify two parses do not replace first."
    p=c.ArgumentParser();p.add('--tag',action='append',env_var='TAGS')
    first=p.parse_result(['--unknown'],config_file_contents='tag=[a,b]',env_vars={})
    p.parse_args(['--tag','next'],env_vars={})
    assert first.namespace.tag==['a','b'] and first.unknown==('--unknown',)
    assert 'a' in json.dumps(first.sources)
    assert 'Action' not in json.dumps(first.sources)

def test_accessors_and_caller_namespace_copied():
    "Verify accessors and caller namespace copied."
    import argparse
    p=c.ArgumentParser();p.add('--tag',action='append')
    namespace=argparse.Namespace(extra=['original'])
    result=p.parse_result(['--tag','x'],namespace=namespace,env_vars={})
    namespace.extra.append('caller');result.namespace.tag.append('view')
    assert result.namespace.extra==['original'] and result.namespace.tag==['x']
    sources=result.sources;sources.clear();assert result.sources

def test_failed_later_parse_keeps_snapshot():
    "Verify failed later parse keeps snapshot."
    import pytest
    p=c.ArgumentParser();p.add('--port',type=int,env_var='PORT')
    result=p.parse_result([],env_vars={'PORT':'9'})
    with pytest.raises(SystemExit):p.parse_result(['--port','bad'],env_vars={})
    assert result.namespace.port==9 and result.sources['environment_variables']['PORT']['value']=='9'
