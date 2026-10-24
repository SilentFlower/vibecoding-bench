"""目录过滤器由每个实例持有独立快照。"""
from mistletoe import Document
from mistletoe.contrib.toc_renderer import TocRenderer


def test_default_instances_are_isolated():
    """修改一个实例不会污染另一个文档。@return None。"""
    with TocRenderer() as first, TocRenderer() as second:
        first.filter_conds.append(lambda value:True)
        assert second.filter_conds==[]
        second.render(Document('## shown\n'))
        assert second._headings==[(2,'shown')]


def test_external_iterables_snapshot_and_order():
    """列表、元组及生成器均按顺序快照且不修改调用者。@return None。"""
    seen=[]
    def condition(value):
        """记录调用次序。@param value 标题。@return 不过滤。"""
        seen.append(value)
        return False
    supplied=[condition]
    with TocRenderer(filter_conds=supplied) as renderer:
        supplied.clear()
        renderer.render(Document('## kept\n'))
        assert seen==['kept'] and renderer._headings==[(2,'kept')]
    with TocRenderer(filter_conds=(fn for fn in [condition])) as renderer:
        renderer.render(Document('## another\n'))
        assert renderer._headings==[(2,'another')]

