"Public regression tests for PYTHON-FRONTMATTER-06-DEV; the complete business contract is in materials/PYTHON-FRONTMATTER-06-DEV-contract.md."
import hashlib
import stat
import tempfile
import unittest
from pathlib import Path
import frontmatter
from frontmatter.atomic import UpdateConflict, atomic_update
from frontmatter.parsing import ParseError


def test_atomic_unicode_update_and_mode():
    "Verify atomic unicode update and mode."
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'doc.md';raw=' \n+++\ncontent="摘要"\n+++\n旧正文'.encode('utf-16-le');path.write_bytes(raw);path.chmod(0o640)
        def change(post):
            "Support the public regression through change."
            post.content='新正文';post['version']=2;return post
        atomic_update(path,change,encoding='utf-16-le',expected_sha256=hashlib.sha256(raw).hexdigest())
        again=frontmatter.load(path,encoding='utf-16-le')
        assert again.content=='新正文' and again.metadata=={'content':'摘要','version':2}
        assert isinstance(again.handler,frontmatter.TOMLHandler) and stat.S_IMODE(path.stat().st_mode)==0o640
        assert sorted(item.name for item in path.parent.iterdir())==['doc.md']


def test_conflict_transform_and_malformed_failures_preserve_input():
    "Verify conflict transform and malformed failures preserve input."
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'doc.md';raw=b'{"content":"meta"}\nbody';path.write_bytes(raw)
        with unittest.TestCase().assertRaises(UpdateConflict):atomic_update(path,lambda post:post,expected_sha256='0'*64)
        with unittest.TestCase().assertRaises(TypeError):atomic_update(path,lambda post:None)
        assert path.read_bytes()==raw
        def race(post):
            "Support the public regression through race."
            path.write_bytes(b'external');return post
        with unittest.TestCase().assertRaises(UpdateConflict):atomic_update(path,race)
        assert path.read_bytes()==b'external'
        path.write_bytes(b'{broken}\nbody')
        with unittest.TestCase().assertRaises(ParseError):atomic_update(path,lambda post:post)
        assert path.read_bytes()==b'{broken}\nbody' and len(list(path.parent.iterdir()))==1

