"""前导空白文档的识别、读取及导出格式一致。"""
import io
import frontmatter
from frontmatter.default_handlers import TOMLHandler, YAMLHandler


def test_leading_toml_preserves_handler_and_business_keys():
    """前导空行不得导致TOML被默认YAML导出。@return None。"""
    text=' \r\n\t\n+++\ncontent="摘要"\nhandler="业务处理"\ntitle="中文"\n+++\n正文'
    assert frontmatter.checks(text)
    post=frontmatter.loads(text)
    assert isinstance(post.handler,TOMLHandler)
    assert post.metadata['content']=='摘要' and post.content=='正文'
    restored=frontmatter.loads(frontmatter.dumps(post))
    assert isinstance(restored.handler,TOMLHandler) and restored.metadata==post.metadata


def test_check_load_and_explicit_handler_agree():
    """文本流及显式处理器继续可用。@return None。"""
    text='\n  \n---\nname: value\n---\nBody'
    assert frontmatter.check(io.StringIO(text))
    assert isinstance(frontmatter.load(io.StringIO(text)).handler,YAMLHandler)
    handler=YAMLHandler()
    assert frontmatter.loads(text,handler=handler).handler is handler
    assert not frontmatter.checks(' \njust body \n')

