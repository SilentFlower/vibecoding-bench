"Public regression tests for CHARDET-O03-DEV; the complete business contract is in materials/CHARDET-O03-DEV-contract.md."
import io
import codecs

def test_stream_position_and_budget():
    "Verify stream position and budget."
    from chardet.files import detect_file
    source = io.BytesIO(b'xxordinary ascii')
    source.seek(2)
    result = detect_file(source, chunk_size=2, max_bytes=4)
    assert result['read_bytes'] == 4 and result['budget_exhausted'] and not result['eof']
    assert source.tell() == 2 and not source.closed

def test_bom_byte_chunks_and_path(tmp_path):
    "Verify bom byte chunks and path."
    from chardet.files import detect_file
    path = tmp_path / 'text'
    path.write_bytes(codecs.BOM_UTF8 + '中文'.encode('utf-8'))
    assert detect_file(path, chunk_size=1)['result']['encoding'] == 'UTF-8-SIG'

def test_zero_no_read_and_eof():
    "Verify zero no read and eof."
    from chardet.files import detect_file
    source = io.BytesIO(b'abc')
    assert detect_file(source, max_bytes=0)['read_bytes'] == 0 and source.tell() == 0
    result = detect_file(source, chunk_size=1, preserve_position=False)
    assert result['eof'] and result['read_bytes'] == 3 and source.tell() == 3
