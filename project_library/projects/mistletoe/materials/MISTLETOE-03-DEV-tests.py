"Public regression tests for MISTLETOE-03-DEV; the complete business contract is in materials/MISTLETOE-03-DEV-contract.md."
from mistletoe import Document
from mistletoe.block_token import List
from mistletoe.contrib.toc_renderer import TocRenderer


def test_no_headings_and_empty_document():
    "Verify no headings and empty document."
    for text in ('','paragraph\n'):
        with TocRenderer() as renderer:
            renderer.render(Document(text))
            assert isinstance(renderer.toc,List)
            assert renderer.toc.children==[]
            assert renderer.render(renderer.toc)==''


def test_all_filtered_and_nonempty():
    "Verify all filtered and nonempty."
    with TocRenderer(depth=1) as renderer:
        renderer.render(Document('# Title\n## Hidden\n'))
        assert renderer.render(renderer.toc)==''
    with TocRenderer(omit_title=False) as renderer:
        renderer.render(Document('# Visible\n'))
        assert 'Visible' in renderer.render(renderer.toc)

