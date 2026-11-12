"Public regression tests for MISTLETOE-02-DEV; the complete business contract is in materials/MISTLETOE-02-DEV-contract.md."
from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer


def test_soft_and_hard_line_breaks():
    "Verify soft and hard line breaks."
    with BaseRenderer() as renderer:
        assert renderer.render(Document('alpha\nbeta'))=='alpha\nbeta'
        assert renderer.render(Document('alpha  \nbeta'))=='alpha\nbeta'


def test_leaf_and_code_values():
    "Verify leaf and code values."
    with BaseRenderer() as renderer:
        assert renderer.render(Document('---\n'))==''
        assert 'code' in renderer.render(Document('```\ncode\n```'))


def test_subclass_override_is_respected():
    "Verify subclass override is respected."
    class Renderer(BaseRenderer):
        "Public regression fixture: Renderer."
        def render_line_break(self, token):
            "Support the public regression through render_line_break."
            return '|'
    with Renderer() as renderer:
        assert renderer.render(Document('a\nb'))=='a|b'

