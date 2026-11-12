"Public regression tests for CHARSET-NORMALIZER-O01-DEV; the complete business contract is in materials/CHARSET-NORMALIZER-O01-DEV-contract.md."
from charset_normalizer.models import CharsetMatch

def test_mutable_model_snapshot():
    "Verify mutable model snapshot."
    source = bytearray(b'ABC')
    match = CharsetMatch(source, 'ascii', 0.0, False, [])
    assert str(match) == 'ABC'
    source[:] = b'XYZ'
    assert match.raw == b'ABC' and str(match) == 'ABC'

def test_view_release_and_copy_metadata():
    "Verify view release and copy metadata."
    from charset_normalizer.buffers import from_buffer
    source = bytearray(b'ordinary ascii')
    view = memoryview(source)
    result = from_buffer(view)
    view.release()
    source[:] = b'changed bytes!!'
    assert str(result['matches'].best()) == 'ordinary ascii' and result['copied'] and result['nbytes'] == 14

def test_bytes_and_noncontiguous():
    "Verify bytes and noncontiguous."
    import pytest
    from charset_normalizer.buffers import from_buffer
    assert from_buffer(b'abc')['copied'] is False
    with pytest.raises(ValueError): from_buffer(memoryview(b'abcdef')[::2])
    with pytest.raises(TypeError): from_buffer('not bytes')
