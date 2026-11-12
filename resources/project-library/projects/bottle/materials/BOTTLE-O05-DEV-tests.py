"Public regression tests for BOTTLE-O05-DEV; the complete business contract is in materials/BOTTLE-O05-DEV-contract.md."
import io
import bottle

def test_atomic_save_and_cursor(tmp_path):
    "Verify atomic save and cursor."
    source = io.BytesIO(b'abcdef')
    source.seek(2)
    upload = bottle.FileUpload(source, 'file', 'x.bin')
    upload.save_atomic(tmp_path)
    assert (tmp_path / 'x.bin').read_bytes() == b'cdef' and source.tell() == 2
    assert list(tmp_path.glob('.bottle-upload-*')) == []

def test_exclusive_keeps_existing(tmp_path):
    "Verify exclusive keeps existing."
    import pytest
    target = tmp_path / 'x.bin'
    target.write_bytes(b'old')
    upload = bottle.FileUpload(io.BytesIO(b'new'), 'file', 'x')
    with pytest.raises(FileExistsError): upload.save_atomic(target)
    assert target.read_bytes() == b'old'
    upload.save_atomic(target, overwrite=True)
    assert target.read_bytes() == b'new'

def test_replace_failure_is_atomic(tmp_path, monkeypatch):
    "Verify replace failure is atomic."
    import pytest
    target = tmp_path / 'x.bin'
    target.write_bytes(b'old')
    def fail(source, destination):
        "Support the public regression through fail."
        raise OSError('replace failed')
    monkeypatch.setattr(bottle.os, 'replace', fail)
    upload = bottle.FileUpload(io.BytesIO(b'new'), 'file', 'x')
    with pytest.raises(OSError): upload.save_atomic(target, overwrite=True)
    assert target.read_bytes() == b'old' and list(tmp_path.glob('.bottle-upload-*')) == []
