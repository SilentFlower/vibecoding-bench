"""真实流读取必须有界且不关闭调用者对象。"""
import io

def test_bounded_read_and_position():
    """评分抽样设置不能代替读取预算。@return None。"""
    from charset_normalizer.streams import from_stream
    class Spy(io.BytesIO):
        """记录实际read参数。"""
        def read(self, size=-1):
            """禁止无界读取。@param size 大小。@return 字节。"""
            assert 0 <= size <= 3
            return super().read(size)
    source = Spy(b'xxplain ascii tail')
    source.seek(2)
    result = from_stream(source, max_bytes=5, read_size=3)
    assert result['read_bytes'] == 5 and not result['eof'] and result['budget_exhausted']
    assert source.tell() == 2 and not source.closed

def test_short_read_and_full_candidate():
    """短读继续到EOF，真实候选文字一致。@return None。"""
    from charset_normalizer.streams import from_stream
    class Short(io.BytesIO):
        """每次最多一字节。"""
        def read(self, size=-1):
            """产生短读。@param size 请求。@return 字节。"""
            return super().read(min(size, 1))
    result = from_stream(Short(b'hello'), max_bytes=20)
    assert result['eof'] and str(result['matches'].best()) == 'hello'

def test_zero_and_text_errors():
    """零不读取，文本流拒绝且恢复位置。@return None。"""
    import pytest
    from charset_normalizer.streams import from_stream
    source = io.BytesIO(b'abc')
    assert from_stream(source, max_bytes=0)['read_bytes'] == 0 and source.tell() == 0
    text = io.StringIO('abc')
    with pytest.raises(TypeError): from_stream(text, max_bytes=4)
    assert text.tell() == 0 and not text.closed
