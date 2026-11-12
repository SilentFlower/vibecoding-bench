"Public regression tests for CSSSELECT-O02-DEV; the complete business contract is in materials/CSSSELECT-O02-DEV-contract.md."
import pytest
import cssselect

def test_mixed_batch_order_and_group():
    "Verify mixed batch order and group."
    from cssselect.batch import translate_many
    rows=list(translate_many([('same','p,a'),('bad','['),('same','div')]))
    assert [r['id'] for r in rows]==['same','bad','same'] and [r['ok'] for r in rows]==[True,False,True]
    assert rows[0]['xpath']==cssselect.GenericTranslator().css_to_xpath('p,a') and rows[1]['error']['phase']=='parse'

def test_laziness_generator_failure_and_failfast():
    "Verify laziness generator failure and failfast."
    from cssselect.batch import translate_many
    def records():
        yield ('a','p')
        raise RuntimeError('upstream')
    result=translate_many(records());assert next(result)['ok']
    with pytest.raises(RuntimeError):next(result)
    with pytest.raises(cssselect.ExpressionError):list(translate_many([('bad',':unknown')],fail_fast=True))

def test_html_prefix_and_empty_batch():
    "Verify html prefix and empty batch."
    from cssselect.batch import translate_many
    assert list(translate_many([]))==[]
    row=next(translate_many([('upper','DIV')],translator=cssselect.HTMLTranslator(),prefix='self::'))
    assert row['xpath']=='self::div'
