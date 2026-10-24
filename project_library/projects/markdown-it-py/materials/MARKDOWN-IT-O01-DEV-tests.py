"Public regression tests for MARKDOWN-IT-O01-DEV; the complete business contract is in materials/MARKDOWN-IT-O01-DEV-contract.md."
from markdown_it import MarkdownIt
import pytest

def test_exception_restores_four_active_chains_and_original_error():
    "Verify exception restores four active chains and original error."
    md=MarkdownIt();before=md.get_active_rules();error=RuntimeError('consumer failed')
    with pytest.raises(RuntimeError) as caught:
        with md.reset_rules():
            md.disable(['emphasis','heading','text_join']);md.inline.ruler2.disable('balance_pairs')
            raise error
    assert caught.value is error and md.get_active_rules()==before
    assert '<em>x</em>' in md.render('*x*')

def test_nested_contexts_restore_their_own_disabled_baseline():
    "Verify nested contexts restore their own disabled baseline."
    md=MarkdownIt().disable('heading');before=md.get_active_rules()
    with md.reset_rules():
        md.disable('emphasis');outer=md.get_active_rules()
        with pytest.raises(ValueError):
            with md.reset_rules():md.disable('link');raise ValueError('nested')
        assert md.get_active_rules()==outer
    assert md.get_active_rules()==before

def test_baseexception_and_normal_exit_both_restore():
    "Verify baseexception and normal exit both restore."
    md=MarkdownIt();before=md.get_active_rules()
    with pytest.raises(KeyboardInterrupt):
        with md.reset_rules():md.disable('emphasis');raise KeyboardInterrupt()
    assert md.get_active_rules()==before
    with md.reset_rules():md.disable('heading')
    assert md.get_active_rules()==before
