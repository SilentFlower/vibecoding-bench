"""公开原子批量配置编辑回归。"""
import os
import pytest
from dotenv import dotenv_values
from dotenv.editing import update_keys

def test_multiple_changes_preserve_non_target_bytes_and_remove_duplicates(tmp_path):
    path = tmp_path/'config.env'
    path.write_bytes(b'# keep\r\nKEEP=x\r\nA=old\r\nA=duplicate\r\nDELETE=yes\r\nTAIL=last')
    assert update_keys(path, {'A':'new','NEW':'value'}, remove=['DELETE']) == (('A','NEW'),('DELETE',))
    assert path.read_bytes() == b"# keep\r\nKEEP=x\r\nA='new'\nTAIL=last\nNEW='value'\n"

def test_quoted_backslash_and_multiline_values_round_trip(tmp_path):
    path=tmp_path/'config.env'
    values={'A':"a\\b'c",'B':'one\ntwo'}
    update_keys(path, values)
    assert dict(dotenv_values(path, interpolate=False)) == values

def test_late_invalid_input_does_not_create_or_modify_files(tmp_path):
    path=tmp_path/'config.env'
    with pytest.raises(ValueError):
        update_keys(path, {'A':'ok','BAD\nKEY':'wrong'})
    assert not path.exists() and list(tmp_path.iterdir()) == []

def test_original_file_mode_survives_replacement(tmp_path):
    path=tmp_path/'config.env'
    path.write_text('A=old\n')
    path.chmod(0o640)
    update_keys(path, {'A':'new'})
    assert path.stat().st_mode & 0o777 == 0o640
