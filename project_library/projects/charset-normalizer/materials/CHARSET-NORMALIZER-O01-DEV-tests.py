"""缓冲生命周期和缓存文本必须保持同一字节快照。"""
from charset_normalizer.models import CharsetMatch

def test_mutable_model_snapshot():
    """直接模型也不能保存可变payload引用。@return None。"""
    source = bytearray(b'ABC')
    match = CharsetMatch(source, 'ascii', 0.0, False, [])
    assert str(match) == 'ABC'
    source[:] = b'XYZ'
    assert match.raw == b'ABC' and str(match) == 'ABC'

def test_view_release_and_copy_metadata():
    """视图释放或底层改写不改变结果。@return None。"""
    from charset_normalizer.buffers import from_buffer
    source = bytearray(b'ordinary ascii')
    view = memoryview(source)
    result = from_buffer(view)
    view.release()
    source[:] = b'changed bytes!!'
    assert str(result['matches'].best()) == 'ordinary ascii' and result['copied'] and result['nbytes'] == 14

def test_bytes_and_noncontiguous():
    """bytes不复制，非连续视图明确拒绝。@return None。"""
    import pytest
    from charset_normalizer.buffers import from_buffer
    assert from_buffer(b'abc')['copied'] is False
    with pytest.raises(ValueError): from_buffer(memoryview(b'abcdef')[::2])
    with pytest.raises(TypeError): from_buffer('not bytes')
