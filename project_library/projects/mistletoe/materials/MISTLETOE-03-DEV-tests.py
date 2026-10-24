"""没有可见标题时仍返回可安全渲染的空目录。"""
from mistletoe import Document
from mistletoe.block_token import List
from mistletoe.contrib.toc_renderer import TocRenderer


def test_no_headings_and_empty_document():
    """普通段落和空文档不会引发IndexError。@return None。"""
    for text in ('','paragraph\n'):
        with TocRenderer() as renderer:
            renderer.render(Document(text))
            assert isinstance(renderer.toc,List)
            assert renderer.toc.children==[]
            assert renderer.render(renderer.toc)==''


def test_all_filtered_and_nonempty():
    """过滤全部和有效目录均使用原列表语义。@return None。"""
    with TocRenderer(depth=1) as renderer:
        renderer.render(Document('# Title\n## Hidden\n'))
        assert renderer.render(renderer.toc)==''
    with TocRenderer(omit_title=False) as renderer:
        renderer.render(Document('# Visible\n'))
        assert 'Visible' in renderer.render(renderer.toc)

