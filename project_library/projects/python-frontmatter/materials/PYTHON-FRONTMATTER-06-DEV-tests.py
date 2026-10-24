"""文档转换完整落盘，错误与冲突不得留下半文件。"""
import hashlib
import stat
import tempfile
import unittest
from pathlib import Path
import frontmatter
from frontmatter.atomic import UpdateConflict, atomic_update
from frontmatter.parsing import ParseError


def test_atomic_unicode_update_and_mode():
    """真实二进制读取、严格解析及同目录替换保持格式。@return None。"""
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'doc.md';raw=' \n+++\ncontent="摘要"\n+++\n旧正文'.encode('utf-16-le');path.write_bytes(raw);path.chmod(0o640)
        def change(post):
            """模拟一次业务编辑。@param post 文档。@return 更新文档。"""
            post.content='新正文';post['version']=2;return post
        atomic_update(path,change,encoding='utf-16-le',expected_sha256=hashlib.sha256(raw).hexdigest())
        again=frontmatter.load(path,encoding='utf-16-le')
        assert again.content=='新正文' and again.metadata=={'content':'摘要','version':2}
        assert isinstance(again.handler,frontmatter.TOMLHandler) and stat.S_IMODE(path.stat().st_mode)==0o640
        assert sorted(item.name for item in path.parent.iterdir())==['doc.md']


def test_conflict_transform_and_malformed_failures_preserve_input():
    """乐观版本、转换失败及坏头部均不得覆盖源。@return None。"""
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'doc.md';raw=b'{"content":"meta"}\nbody';path.write_bytes(raw)
        with unittest.TestCase().assertRaises(UpdateConflict):atomic_update(path,lambda post:post,expected_sha256='0'*64)
        with unittest.TestCase().assertRaises(TypeError):atomic_update(path,lambda post:None)
        assert path.read_bytes()==raw
        def race(post):
            """模拟转换期间外部编辑。@param post 原文档。@return 原文档。"""
            path.write_bytes(b'external');return post
        with unittest.TestCase().assertRaises(UpdateConflict):atomic_update(path,race)
        assert path.read_bytes()==b'external'
        path.write_bytes(b'{broken}\nbody')
        with unittest.TestCase().assertRaises(ParseError):atomic_update(path,lambda post:post)
        assert path.read_bytes()==b'{broken}\nbody' and len(list(path.parent.iterdir()))==1

