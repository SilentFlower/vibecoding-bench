"""归一化仅在完整编码成功后原子替换目标。"""
import os
import stat

def test_success_and_permissions(tmp_path):
    """实际规范化内容且保留目标权限。@param tmp_path 临时目录。@return None。"""
    from charset_normalizer.atomic import normalize_file_atomic
    source = tmp_path / 'text'
    source.write_bytes('café'.encode('latin-1'))
    source.chmod(0o640)
    result = normalize_file_atomic(source, cp_isolation=['latin-1'])
    assert source.read_text() == 'café' and result['unencodable_codepoints'] == 0
    assert stat.S_IMODE(source.stat().st_mode) == 0o640

def test_encoding_failure_preserves_source(tmp_path):
    """目标无法编码时不改变旧字节。@param tmp_path 临时目录。@return None。"""
    import pytest
    from charset_normalizer.atomic import normalize_file_atomic
    source = tmp_path / 'text'
    original = '中文'.encode('utf-8')
    source.write_bytes(original)
    with pytest.raises(UnicodeEncodeError): normalize_file_atomic(source, encoding='ascii', cp_isolation=['utf-8'])
    assert source.read_bytes() == original and list(tmp_path.glob('.charset-normalize-*')) == []

def test_replace_failure_and_separate_output(tmp_path, monkeypatch):
    """替换失败保留旧目标，清理仅本次临时文件。@param tmp_path 临时目录。@param monkeypatch 故障注入。@return None。"""
    import pytest
    import charset_normalizer.atomic as module
    source, destination = tmp_path / 'source', tmp_path / 'target'
    source.write_bytes(b'new')
    destination.write_bytes(b'old')
    def fail(left, right):
        """模拟发布错误。@param left 临时。@param right 目标。@return 不返回。"""
        raise OSError('replace')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError): module.normalize_file_atomic(source, destination)
    assert source.read_bytes() == b'new' and destination.read_bytes() == b'old' and list(tmp_path.glob('.charset-normalize-*')) == []
