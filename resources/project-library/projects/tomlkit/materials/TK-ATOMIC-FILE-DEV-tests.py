"Public regression tests for TK-ATOMIC-FILE-DEV; the complete business contract is in materials/TK-ATOMIC-FILE-DEV-contract.md."
import pytest
import tomlkit
from tomlkit.files import load_with_digest,atomic_save,StaleDocumentError

def test_edit_preserves_comments_and_returns_current_digest(tmp_path):
    path=tmp_path/'app.toml';path.write_text('# keep\na=1\n')
    document,digest=load_with_digest(path);document['a']=2
    new=atomic_save(document,path,expected_digest=digest)
    assert '# keep' in path.read_text() and load_with_digest(path)[1]==new and new!=digest

def test_stale_disk_change_is_not_overwritten(tmp_path):
    path=tmp_path/'app.toml';path.write_text('a=1\n')
    document,digest=load_with_digest(path);path.write_text('a=3\n')
    with pytest.raises(StaleDocumentError):
        atomic_save(document,path,expected_digest=digest)
    assert path.read_text()=='a=3\n' and list(tmp_path.iterdir())==[path]

def test_replace_failure_preserves_bytes_and_cleans_temporary(tmp_path,monkeypatch):
    path=tmp_path/'app.toml';path.write_text('a=1\n');path.chmod(0o640)
    def broken(*args):
        raise OSError('synthetic')
    monkeypatch.setattr('os.replace',broken)
    with pytest.raises(OSError):
        atomic_save(tomlkit.parse('a=2\n'),path)
    assert path.read_text()=='a=1\n' and path.stat().st_mode&0o777==0o640 and list(tmp_path.iterdir())==[path]

def test_new_file_is_private_and_unicode_roundtrips(tmp_path):
    path=tmp_path/'app.toml'
    atomic_save(tomlkit.parse('name="雪"\n'),path)
    assert path.stat().st_mode&0o777==0o600 and load_with_digest(path)[0]['name']=='雪'
