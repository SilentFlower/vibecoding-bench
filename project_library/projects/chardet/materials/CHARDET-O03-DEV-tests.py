"""文件检测实际读取预算、BOM分块和流所有权。"""
import io
import codecs

def test_stream_position_and_budget():
    """预算不多读，默认恢复原位置。@return None。"""
    from chardet.files import detect_file
    source = io.BytesIO(b'xxordinary ascii')
    source.seek(2)
    result = detect_file(source, chunk_size=2, max_bytes=4)
    assert result['read_bytes'] == 4 and result['budget_exhausted'] and not result['eof']
    assert source.tell() == 2 and not source.closed

def test_bom_byte_chunks_and_path(tmp_path):
    """一字节文件读取复用已修复的BOM核心。@param tmp_path 临时目录。@return None。"""
    from chardet.files import detect_file
    path = tmp_path / 'text'
    path.write_bytes(codecs.BOM_UTF8 + '中文'.encode('utf-8'))
    assert detect_file(path, chunk_size=1)['result']['encoding'] == 'UTF-8-SIG'

def test_zero_no_read_and_eof():
    """零预算不读取，完整ASCII流才报告EOF。@return None。"""
    from chardet.files import detect_file
    source = io.BytesIO(b'abc')
    assert detect_file(source, max_bytes=0)['read_bytes'] == 0 and source.tell() == 0
    result = detect_file(source, chunk_size=1, preserve_position=False)
    assert result['eof'] and result['read_bytes'] == 3 and source.tell() == 3
