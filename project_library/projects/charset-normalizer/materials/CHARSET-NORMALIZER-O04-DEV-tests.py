"Public regression tests for CHARSET-NORMALIZER-O04-DEV; the complete business contract is in materials/CHARSET-NORMALIZER-O04-DEV-contract.md."
import bz2
import gzip
import lzma

def test_three_formats_same_text(tmp_path):
    "Verify three formats same text."
    from charset_normalizer.compressed import from_compressed_path
    payload = 'Hello compressed 中文'.encode('utf-8')
    for format, compress in [('gzip', gzip.compress), ('bz2', bz2.compress), ('xz', lzma.compress)]:
        path = tmp_path / format
        path.write_bytes(compress(payload))
        result = from_compressed_path(path, format=format, max_bytes=len(payload), cp_isolation=['utf-8'])
        assert str(result['matches'].best()) == payload.decode('utf-8') and result['decoded_bytes'] == len(payload)

def test_over_budget_and_original(tmp_path):
    "Verify over budget and original."
    import pytest
    from charset_normalizer.compressed import from_compressed_path
    path = tmp_path / 'text.gz'
    original = gzip.compress(b'x' * 100)
    path.write_bytes(original)
    with pytest.raises(ValueError): from_compressed_path(path, format='gzip', max_bytes=5)
    assert path.read_bytes() == original

def test_empty_and_truncated(tmp_path):
    "Verify empty and truncated."
    import pytest
    from charset_normalizer.compressed import from_compressed_path
    path = tmp_path / 'empty.gz'
    path.write_bytes(gzip.compress(b''))
    assert from_compressed_path(path, format='gzip', max_bytes=0)['decoded_bytes'] == 0
    path.write_bytes(gzip.compress(b'abc')[:-4])
    with pytest.raises((EOFError, OSError)): from_compressed_path(path, format='gzip', max_bytes=10)
