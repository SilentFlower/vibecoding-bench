"""三种实际压缩文本读取必须有严格解压预算。"""
import bz2
import gzip
import lzma

def test_three_formats_same_text(tmp_path):
    """gzip/bz2/xz均调用真实检测得到同样文字。@param tmp_path 临时目录。@return None。"""
    from charset_normalizer.compressed import from_compressed_path
    payload = 'Hello compressed 中文'.encode('utf-8')
    for format, compress in [('gzip', gzip.compress), ('bz2', bz2.compress), ('xz', lzma.compress)]:
        path = tmp_path / format
        path.write_bytes(compress(payload))
        result = from_compressed_path(path, format=format, max_bytes=len(payload), cp_isolation=['utf-8'])
        assert str(result['matches'].best()) == payload.decode('utf-8') and result['decoded_bytes'] == len(payload)

def test_over_budget_and_original(tmp_path):
    """超限拒绝且压缩原文件不改变。@param tmp_path 临时目录。@return None。"""
    import pytest
    from charset_normalizer.compressed import from_compressed_path
    path = tmp_path / 'text.gz'
    original = gzip.compress(b'x' * 100)
    path.write_bytes(original)
    with pytest.raises(ValueError): from_compressed_path(path, format='gzip', max_bytes=5)
    assert path.read_bytes() == original

def test_empty_and_truncated(tmp_path):
    """空载荷可识别，损坏尾部不返回部分成功。@param tmp_path 临时目录。@return None。"""
    import pytest
    from charset_normalizer.compressed import from_compressed_path
    path = tmp_path / 'empty.gz'
    path.write_bytes(gzip.compress(b''))
    assert from_compressed_path(path, format='gzip', max_bytes=0)['decoded_bytes'] == 0
    path.write_bytes(gzip.compress(b'abc')[:-4])
    with pytest.raises((EOFError, OSError)): from_compressed_path(path, format='gzip', max_bytes=10)
