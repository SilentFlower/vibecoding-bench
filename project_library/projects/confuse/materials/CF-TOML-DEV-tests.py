"""公开TOML来源实际文件回归。"""
from datetime import date
import pytest
from confuse import Configuration,ConfigReadError
from confuse.toml_source import TomlSource

def test_tables_dates_and_source_metadata(tmp_path):
    file=tmp_path/'config.toml';file.write_text('[service]\nports=[80,443]\nday=2026-01-02\n')
    source=TomlSource(file,default=True,base_for_paths=True)
    assert source['service']=={'ports':[80,443],'day':date(2026,1,2)}
    assert source.filename==str(file) and source.default and source.base_for_paths

def test_successful_reload_removes_keys_and_preserves_identity(tmp_path):
    file=tmp_path/'c.toml';file.write_text('old=1\nkeep=2\n');source=TomlSource(file)
    config=Configuration('app',read=False);config.add({'old':9});config.set(source)
    file.write_text('keep=3\n');config.reload()
    assert config.sources[0] is source and config['old'].get()==9 and config['keep'].get()==3

def test_bad_toml_preserves_last_valid_data(tmp_path):
    file=tmp_path/'c.toml';file.write_text('value=4\n');source=TomlSource(file)
    file.write_text('value=[\n')
    with pytest.raises(ConfigReadError): source.load()
    assert dict(source)=={'value':4}

def test_optional_missing_becomes_empty_but_parse_error_is_not_optional(tmp_path):
    file=tmp_path/'c.toml';source=TomlSource(file,optional=True);assert source=={}
    file.write_text('v=1');source.load();file.unlink();source.load();assert source=={}
    file.write_text('v=[')
    with pytest.raises(ConfigReadError): source.load()
