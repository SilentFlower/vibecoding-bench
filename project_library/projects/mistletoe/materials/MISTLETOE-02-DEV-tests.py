"""基础渲染器具备可预测的叶节点文本语义。"""
from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer


def test_soft_and_hard_line_breaks():
    """普通换行与硬换行保留文本分隔。@return None。"""
    with BaseRenderer() as renderer:
        assert renderer.render(Document('alpha\nbeta'))=='alpha\nbeta'
        assert renderer.render(Document('alpha  \nbeta'))=='alpha\nbeta'


def test_leaf_and_code_values():
    """分隔线安全为空，代码内容不会因缺子节点被吞。@return None。"""
    with BaseRenderer() as renderer:
        assert renderer.render(Document('---\n'))==''
        assert 'code' in renderer.render(Document('```\ncode\n```'))


def test_subclass_override_is_respected():
    """子类对分隔行为的决定优先。@return None。"""
    class Renderer(BaseRenderer):
        """为当前业务使用竖线分隔。"""
        def render_line_break(self, token):
            """提供业务分隔符。@param token 节点。@return 分隔符。"""
            return '|'
    with Renderer() as renderer:
        assert renderer.render(Document('a\nb'))=='a|b'

