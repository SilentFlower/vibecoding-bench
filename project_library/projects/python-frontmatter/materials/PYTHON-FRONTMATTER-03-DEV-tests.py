"""JSON边界由语法确定，不能按独立花括号行截断。"""
import json
import unittest
import frontmatter
from frontmatter.default_handlers import JSONHandler


def test_compact_empty_and_nested_objects():
    """紧凑与嵌套对象只消费一个完整JSON值。@return None。"""
    for header in ({},{'content':'摘要','handler':'业务','nested':{'list':[{'a':'{x}'}]}}):
        post=frontmatter.loads(json.dumps(header)+'\nBody {not JSON}')
        assert isinstance(post.handler,JSONHandler)
        assert post.metadata==header and post.content=='Body {not JSON}'
        assert frontmatter.loads(frontmatter.dumps(post)).metadata==header


def test_nested_pretty_and_invalid_json():
    """内部闭括号行不是外层终点；错误JSON不得静默吃掉正文。@return None。"""
    raw='{\n"nested": {\n"x": 1\n}\n}\nBody'
    assert frontmatter.loads(raw).metadata=={'nested':{'x':1}}
    with unittest.TestCase().assertRaises(json.JSONDecodeError):frontmatter.loads('{\n"x": BAD\n}\nbody')
    assert frontmatter.loads('no JSON here').content=='no JSON here'

