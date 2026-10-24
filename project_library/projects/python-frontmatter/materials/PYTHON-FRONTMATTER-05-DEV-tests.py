"Public regression tests for PYTHON-FRONTMATTER-05-DEV; the complete business contract is in materials/PYTHON-FRONTMATTER-05-DEV-contract.md."
import io
import unittest
import frontmatter
from frontmatter.default_handlers import JSONHandler,TOMLHandler


def test_binary_read_current_cursor_and_encoding():
    "Verify binary read current cursor and encoding."
    raw='  \n+++\ncontent="摘要"\n+++\n正文'.encode('utf-16-le')
    stream=io.BytesIO(b'prefix'+raw);stream.seek(6)
    post=frontmatter.load(stream,encoding='utf-16-le')
    assert isinstance(post.handler,TOMLHandler) and post.metadata['content']=='摘要'
    assert post.content=='正文' and not stream.closed


def test_binary_dump_roundtrip_and_error_is_not_retried():
    "Verify binary dump roundtrip and error is not retried."
    post=frontmatter.loads('{"content":"摘要"}\n正文')
    stream=io.BytesIO();frontmatter.dump(post,stream,encoding='utf-16-le',ensure_ascii=False)
    assert not stream.closed
    stream.seek(0);again=frontmatter.load(stream,encoding='utf-16-le')
    assert isinstance(again.handler,JSONHandler) and again.metadata==post.metadata and again.content=='正文'
    text=io.StringIO();frontmatter.dump(post,text,ensure_ascii=False)
    assert isinstance(text.getvalue(),str)
    with unittest.TestCase().assertRaises(UnicodeDecodeError):frontmatter.load(io.BytesIO(b'\xff'))

