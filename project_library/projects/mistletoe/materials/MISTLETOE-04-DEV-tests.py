"Public regression tests for MISTLETOE-04-DEV; the complete business contract is in materials/MISTLETOE-04-DEV-contract.md."
from mistletoe import Document
from mistletoe.contrib.toc_renderer import TocRenderer


def test_default_instances_are_isolated():
    "Verify default instances are isolated."
    with TocRenderer() as first, TocRenderer() as second:
        first.filter_conds.append(lambda value:True)
        assert second.filter_conds==[]
        second.render(Document('## shown\n'))
        assert second._headings==[(2,'shown')]


def test_external_iterables_snapshot_and_order():
    "Verify external iterables snapshot and order."
    seen=[]
    def condition(value):
        "Support the public regression through condition."
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

