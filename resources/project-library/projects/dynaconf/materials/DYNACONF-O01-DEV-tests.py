"Public regression tests for DYNACONF-O01-DEV; the complete business contract is in materials/DYNACONF-O01-DEV-contract.md."
from dynaconf import Dynaconf
from types import ModuleType
import pytest

def test_str_pathlike_and_glob_load_actual_files(tmp_path):
    "Verify str pathlike and glob load actual files."
    one=tmp_path/'one.json';one.write_text('{"VALUE":1}');two=tmp_path/'two.json';two.write_text('{"VALUE":2}')
    for path in [str(one),one]:
        settings=Dynaconf(environments=False);settings.load_file(path,silent=False);assert settings.VALUE==1
    settings=Dynaconf(environments=False);settings.load_file(str(tmp_path/'*.json'));assert settings.VALUE==2

def test_invalid_arguments_and_mixed_sequence_reject_before_loading(tmp_path):
    "Verify invalid arguments and mixed sequence reject before loading."
    path=tmp_path/'one.json';path.write_text('{"VALUE":1}')
    for silent in [True,False]:
        for invalid in [ModuleType('fake'),{},42,b'bytes',[path,42]]:
            settings=Dynaconf(environments=False)
            with pytest.raises(TypeError):settings.load_file(invalid,silent=silent)
            assert settings.get('VALUE') is None

def test_bad_path_protocol_empty_lists_and_no_match_keep_explicit_boundaries():
    "Verify bad path protocol empty lists and no match keep explicit boundaries."
    class Bad:
        "Public regression fixture: Bad."
        def __fspath__(self):return 42
    settings=Dynaconf(environments=False)
    with pytest.raises(TypeError):settings.load_file(Bad())
    assert settings.load_file([]) is None and settings.load_file(None) is None
    assert settings.load_file('unmatched-ordinary-*.json') is None
