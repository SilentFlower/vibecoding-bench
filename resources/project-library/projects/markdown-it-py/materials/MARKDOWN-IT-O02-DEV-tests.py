"Public regression tests for MARKDOWN-IT-O02-DEV; the complete business contract is in materials/MARKDOWN-IT-O02-DEV-contract.md."
from markdown_it import MarkdownIt
import pytest

def test_generator_enables_block_inline_and_second_inline_chain():
    "Verify generator enables block inline and second inline chain."
    names=['table','strikethrough','emphasis']
    expected=MarkdownIt().enable(names)
    actual=MarkdownIt().enable(name for name in names)
    assert actual.get_active_rules()==expected.get_active_rules()
    text='~~gone~~\n\na|b\n-| -\nx|y'
    assert actual.render(text)==expected.render(text) and '<s>gone</s>' in actual.render(text)

def test_generator_disables_and_unknown_detection_is_not_consumed():
    "Verify generator disables and unknown detection is not consumed."
    names=['heading','emphasis','image']
    actual=MarkdownIt().disable(iter(names));expected=MarkdownIt().disable(names)
    assert actual.get_active_rules()==expected.get_active_rules()
    with pytest.raises(ValueError):MarkdownIt().enable(name for name in ['not-a-rule'])
    with pytest.raises(ValueError):MarkdownIt().disable(iter(['not-a-rule']))
    assert MarkdownIt().enable(iter(['not-a-rule']),ignoreInvalid=True)

def test_iterating_failure_happens_before_any_rule_changes():
    "Verify iterating failure happens before any rule changes."
    def broken():yield 'text_join';raise RuntimeError('input failed')
    md=MarkdownIt();before=md.get_active_rules()
    with pytest.raises(RuntimeError):md.disable(broken())
    assert md.get_active_rules()==before
    md.enable(iter([]));md.disable(iter([]));assert md.get_active_rules()==before
