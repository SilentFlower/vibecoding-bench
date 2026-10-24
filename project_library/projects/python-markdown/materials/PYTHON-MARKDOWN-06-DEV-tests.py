"""路径、文本/二进制流显式编码并保留调用方所有权。"""
import io
import tempfile
import unittest
from pathlib import Path
from markdown.documents import convert_file


def test_pathlike_input_output_and_independent_encodings():
    """真正读取Path并从UTF16文档写UTF8 HTML，返回结构化目录。@return None。"""
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'input.md';output=Path(temporary)/'output.html'
        source.write_bytes('# 中文'.encode('utf-16-le'))
        result=convert_file(source,output,input_encoding='utf-16-le',output_encoding='utf-8',extensions=['markdown.extensions.toc'])
        assert output.read_text() == result.html and result.toc_tokens[0]['name']=='中文'


def test_stream_cursor_ownership_and_encoding_failure_preserves_file():
    """流不倒带、不关闭，显式close输入可选，失败不截断旧输出。@return None。"""
    stream=io.BytesIO(b'ignored# Title');stream.seek(7);output=io.BytesIO()
    result=convert_file(stream,output,output_encoding='utf-16-le')
    assert output.getvalue().decode('utf-16-le')==result.html and not stream.closed and not output.closed
    text=io.StringIO('body');convert_file(text,close_input=True);assert text.closed
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'out';path.write_bytes(b'old')
        with unittest.TestCase().assertRaises(UnicodeEncodeError):convert_file(io.StringIO('中文'),path,output_encoding='ascii')
        assert path.read_bytes()==b'old'

