"Public regression tests for TD-ATOMIC-STORAGE-DEV; the complete business contract is in materials/TD-ATOMIC-STORAGE-DEV-contract.md."
import pytest
from tinydb import TinyDB
from tinydb.atomic import AtomicJSONStorage

def test_tinydb_roundtrip_reopen_and_smaller_database(tmp_path):
    path=tmp_path/'db.json'
    with TinyDB(path,storage=AtomicJSONStorage) as db:
        db.insert_multiple([{'value':'long'*100},{'value':'short'}])
    with TinyDB(path,storage=AtomicJSONStorage) as db:
        assert len(db)==2
        db.remove(doc_ids=[1])
    with TinyDB(path,storage=AtomicJSONStorage) as db:
        assert db.all()==[{'value':'short'}]

def test_serialization_failure_preserves_old_bytes(tmp_path):
    path=tmp_path/'db.json'
    storage=AtomicJSONStorage(path)
    storage.write({'table':{}})
    before=path.read_bytes()
    with pytest.raises(TypeError):
        storage.write({'bad':object()})
    assert path.read_bytes()==before and list(tmp_path.iterdir())==[path]

def test_replace_failure_cleans_temporary_and_preserves_mode(tmp_path,monkeypatch):
    path=tmp_path/'db.json'
    path.write_text('{}');path.chmod(0o640)
    storage=AtomicJSONStorage(path)
    def broken(*args):
        raise OSError('synthetic')
    monkeypatch.setattr('os.replace',broken)
    with pytest.raises(OSError):
        storage.write({'new':{}})
    assert path.read_text()=='{}' and path.stat().st_mode&0o777==0o640 and list(tmp_path.iterdir())==[path]

def test_missing_empty_closed_and_symlink_are_explicit(tmp_path):
    path=tmp_path/'missing.json'
    storage=AtomicJSONStorage(path)
    assert storage.read() is None and not path.exists()
    storage.close();storage.close()
    with pytest.raises(ValueError):
        storage.read()
    link=tmp_path/'link.json';link.symlink_to(path)
    with pytest.raises(ValueError):
        AtomicJSONStorage(link)
