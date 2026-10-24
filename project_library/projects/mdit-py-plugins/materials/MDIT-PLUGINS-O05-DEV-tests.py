"""点结束符不进入metadata且在EOF也真正关闭。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

def test_dot_terminator_metadata_content_and_body_map():
    """内容仅含数据，map包括结束行而正文第一行不能被吞。@return None。"""
    md=MarkdownIt().use(front_matter_plugin)
    tokens=md.parse('---\na: 1\n...\n# Body')
    assert tokens[0].type=='front_matter' and tokens[0].content=='a: 1'
    assert tokens[0].map==[0,3] and tokens[0].hidden
    assert md.render('---\na: 1\n...\n# Body')=='\n<h1>Body</h1>\n'

def test_eof_empty_metadata_and_trailing_spaces():
    """结束符在最后一行、空数据和允许尾空白均关闭。@return None。"""
    md=MarkdownIt().use(front_matter_plugin)
    for source,content in [('---\na: 1\n...','a: 1'),('---\n...',''),('---\na: 1\n...  \t','a: 1')]:
        tokens=md.parse(source)
        assert len(tokens)==1 and tokens[0].type=='front_matter' and tokens[0].content==content
        assert tokens[0].map==[0,len(source.splitlines())]

def test_long_dots_unclosed_noninitial_and_dash_defaults_stay_distinct():
    """四点不是结束符，非文档首行不当metadata，原破折号保持。@return None。"""
    md=MarkdownIt().use(front_matter_plugin)
    assert all(token.type!='front_matter' for token in md.parse('---\na: 1\n....'))
    assert all(token.type!='front_matter' for token in md.parse('text\n\n---\na: 1\n...'))
    assert md.parse('---\na: 1\n---')[0].content=='a: 1'
