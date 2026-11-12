"Public regression tests for DYNACONF-O04-DEV; the complete business contract is in materials/DYNACONF-O04-DEV-contract.md."
from dynaconf import Dynaconf
import pytest

def test_extensionless_json_toml_yaml_load_real_content(tmp_path):
    "Verify extensionless json toml yaml load real content."
    for format,text in [('json','{"VALUE":1}'),('toml','VALUE = 2'),('yaml','VALUE: 3')]:
        path=tmp_path/('config-'+format);path.write_text(text)
        settings=Dynaconf(environments=False);settings.load_file(path,format=format,silent=False)
        assert settings.VALUE=={'json':1,'toml':2,'yaml':3}[format] and str(path) in settings._loaded_files

def test_environment_sections_key_filter_extension_override_and_source_metadata(tmp_path):
    "Verify environment sections key filter extension override and source metadata."
    path=tmp_path/'looks-like.yaml';path.write_text('{"default":{"VALUE":1,"OTHER":2},"production":{"VALUE":9}}')
    settings=Dynaconf(environments=True,env='production');settings.load_file(path,format='json',key='VALUE')
    assert settings.VALUE==9 and settings.get('OTHER') is None
    assert any(getattr(metadata,'identifier',None)==str(path) for metadata in settings._loaded_by_loaders)

def test_unknown_disabled_loader_and_bad_syntax_are_explicit(tmp_path):
    "Verify unknown disabled loader and bad syntax are explicit."
    path=tmp_path/'plain';path.write_text('bad-json')
    settings=Dynaconf(environments=False)
    with pytest.raises(ValueError):settings.load_file(path,format='python.module')
    with pytest.raises(ValueError):settings.load_file(path,format='json',silent=False)
    disabled=Dynaconf(environments=False,core_loaders=['TOML'])
    with pytest.raises(ValueError):disabled.load_file(path,format='json')
