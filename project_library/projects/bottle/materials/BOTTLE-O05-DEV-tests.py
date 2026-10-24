"""上传原子发布保持旧文件、竞争者和输入位置。"""
import io
import bottle

def test_atomic_save_and_cursor(tmp_path):
    """成功后内容和游标保持，目录目标可用。@param tmp_path 临时目录。@return None。"""
    source = io.BytesIO(b'abcdef')
    source.seek(2)
    upload = bottle.FileUpload(source, 'file', 'x.bin')
    upload.save_atomic(tmp_path)
    assert (tmp_path / 'x.bin').read_bytes() == b'cdef' and source.tell() == 2
    assert list(tmp_path.glob('.bottle-upload-*')) == []

def test_exclusive_keeps_existing(tmp_path):
    """排他保存不能覆盖已有目标。@param tmp_path 临时目录。@return None。"""
    import pytest
    target = tmp_path / 'x.bin'
    target.write_bytes(b'old')
    upload = bottle.FileUpload(io.BytesIO(b'new'), 'file', 'x')
    with pytest.raises(FileExistsError): upload.save_atomic(target)
    assert target.read_bytes() == b'old'
    upload.save_atomic(target, overwrite=True)
    assert target.read_bytes() == b'new'

def test_replace_failure_is_atomic(tmp_path, monkeypatch):
    """发布失败不留下半文件并清理本次临时文件。@param tmp_path 临时目录。@param monkeypatch 故障注入。@return None。"""
    import pytest
    target = tmp_path / 'x.bin'
    target.write_bytes(b'old')
    def fail(source, destination):
        """模拟发布故障。@param source 临时文件。@param destination 目标。@return 不返回。"""
        raise OSError('replace failed')
    monkeypatch.setattr(bottle.os, 'replace', fail)
    upload = bottle.FileUpload(io.BytesIO(b'new'), 'file', 'x')
    with pytest.raises(OSError): upload.save_atomic(target, overwrite=True)
    assert target.read_bytes() == b'old' and list(tmp_path.glob('.bottle-upload-*')) == []
