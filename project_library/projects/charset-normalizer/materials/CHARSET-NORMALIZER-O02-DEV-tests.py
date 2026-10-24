"Public regression tests for CHARSET-NORMALIZER-O02-DEV; the complete business contract is in materials/CHARSET-NORMALIZER-O02-DEV-contract.md."
import io

def test_bounded_read_and_position():
    "Verify bounded read and position."
    from charset_normalizer.streams import from_stream
    class Spy(io.BytesIO):
        "Public regression fixture: Spy."
        def read(self, size=-1):
            "Support the public regression through read."
            assert 0 <= size <= 3
            return super().read(size)
    source = Spy(b'xxplain ascii tail')
    source.seek(2)
    result = from_stream(source, max_bytes=5, read_size=3)
    assert result['read_bytes'] == 5 and not result['eof'] and result['budget_exhausted']
    assert source.tell() == 2 and not source.closed

def test_short_read_and_full_candidate():
    "Verify short read and full candidate."
    from charset_normalizer.streams import from_stream
    class Short(io.BytesIO):
        "Public regression fixture: Short."
        def read(self, size=-1):
            "Support the public regression through read."
            return super().read(min(size, 1))
    result = from_stream(Short(b'hello'), max_bytes=20)
    assert result['eof'] and str(result['matches'].best()) == 'hello'

def test_zero_and_text_errors():
    "Verify zero and text errors."
    import pytest
    from charset_normalizer.streams import from_stream
    source = io.BytesIO(b'abc')
    assert from_stream(source, max_bytes=0)['read_bytes'] == 0 and source.tell() == 0
    text = io.StringIO('abc')
    with pytest.raises(TypeError): from_stream(text, max_bytes=4)
    assert text.tell() == 0 and not text.closed
