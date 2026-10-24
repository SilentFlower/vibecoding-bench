"Public regression tests for PYTHON-MARKDOWN-06-DEV; the complete business contract is in materials/PYTHON-MARKDOWN-06-DEV-contract.md."
import io
import tempfile
import unittest
from pathlib import Path
from markdown.documents import convert_file


def test_pathlike_input_output_and_independent_encodings():
    "Verify pathlike input output and independent encodings."
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'input.md';output=Path(temporary)/'output.html'
        source.write_bytes('# 中文'.encode('utf-16-le'))
        result=convert_file(source,output,input_encoding='utf-16-le',output_encoding='utf-8',extensions=['markdown.extensions.toc'])
        assert output.read_text() == result.html and result.toc_tokens[0]['name']=='中文'


def test_stream_cursor_ownership_and_encoding_failure_preserves_file():
    "Verify stream cursor ownership and encoding failure preserves file."
    stream=io.BytesIO(b'ignored# Title');stream.seek(7);output=io.BytesIO()
    result=convert_file(stream,output,output_encoding='utf-16-le')
    assert output.getvalue().decode('utf-16-le')==result.html and not stream.closed and not output.closed
    text=io.StringIO('body');convert_file(text,close_input=True);assert text.closed
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'out';path.write_bytes(b'old')
        with unittest.TestCase().assertRaises(UnicodeEncodeError):convert_file(io.StringIO('中文'),path,output_encoding='ascii')
        assert path.read_bytes()==b'old'

