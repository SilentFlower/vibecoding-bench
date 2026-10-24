"""批次隔离错误，真实CSS组中的逗号保持语义。"""
import pytest
import cssselect

def test_mixed_batch_order_and_group():
    """失败不吞掉后续规则或重复ID。@return None。"""
    from cssselect.batch import translate_many
    rows=list(translate_many([('same','p,a'),('bad','['),('same','div')]))
    assert [r['id'] for r in rows]==['same','bad','same'] and [r['ok'] for r in rows]==[True,False,True]
    assert rows[0]['xpath']==cssselect.GenericTranslator().css_to_xpath('p,a') and rows[1]['error']['phase']=='parse'

def test_laziness_generator_failure_and_failfast():
    """只消费请求项，输入生成器异常不能伪装翻译失败。@return None。"""
    from cssselect.batch import translate_many
    def records():
        yield ('a','p')
        raise RuntimeError('upstream')
    result=translate_many(records());assert next(result)['ok']
    with pytest.raises(RuntimeError):next(result)
    with pytest.raises(cssselect.ExpressionError):list(translate_many([('bad',':unknown')],fail_fast=True))

def test_html_prefix_and_empty_batch():
    """调用方真实翻译配置保留，空批次不产生记录。@return None。"""
    from cssselect.batch import translate_many
    assert list(translate_many([]))==[]
    row=next(translate_many([('upper','DIV')],translator=cssselect.HTMLTranslator(),prefix='self::'))
    assert row['xpath']=='self::div'
