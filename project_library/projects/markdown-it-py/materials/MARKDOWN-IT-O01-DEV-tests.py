"""规则上下文异常退出也必须还原所有真实规则链。"""
from markdown_it import MarkdownIt
import pytest

def test_exception_restores_four_active_chains_and_original_error():
    """进入前快照与退出后相等，原异常对象原样传播。@return None。"""
    md=MarkdownIt();before=md.get_active_rules();error=RuntimeError('consumer failed')
    with pytest.raises(RuntimeError) as caught:
        with md.reset_rules():
            md.disable(['emphasis','heading','text_join']);md.inline.ruler2.disable('balance_pairs')
            raise error
    assert caught.value is error and md.get_active_rules()==before
    assert '<em>x</em>' in md.render('*x*')

def test_nested_contexts_restore_their_own_disabled_baseline():
    """内层异常恢复外层状态，外层退出恢复最初已禁用集合。@return None。"""
    md=MarkdownIt().disable('heading');before=md.get_active_rules()
    with md.reset_rules():
        md.disable('emphasis');outer=md.get_active_rules()
        with pytest.raises(ValueError):
            with md.reset_rules():md.disable('link');raise ValueError('nested')
        assert md.get_active_rules()==outer
    assert md.get_active_rules()==before

def test_baseexception_and_normal_exit_both_restore():
    """取消类异常也收口，普通上下文仍沿既有语义。@return None。"""
    md=MarkdownIt();before=md.get_active_rules()
    with pytest.raises(KeyboardInterrupt):
        with md.reset_rules():md.disable('emphasis');raise KeyboardInterrupt()
    assert md.get_active_rules()==before
    with md.reset_rules():md.disable('heading')
    assert md.get_active_rules()==before
