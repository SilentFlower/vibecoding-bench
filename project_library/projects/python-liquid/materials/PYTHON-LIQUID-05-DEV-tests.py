"Public regression tests for PYTHON-LIQUID-05-DEV; the complete business contract is in materials/PYTHON-LIQUID-05-DEV-contract.md."
import json
import unittest
from liquid.template_bundle import make_bundle,load_bundle

def test_canonical_snapshot_and_real_include_render():
    "Verify canonical snapshot and real include render."
    sources={'report':'Report:{% render "row", value: item %}','row':'[{{value}}]'}
    text=make_bundle(sources,['report']);sources['row']='changed';bundle=load_bundle(text)
    assert bundle.environment().get_template('report').render(item='茶')=='Report:[茶]'
    assert text==make_bundle({'row':'[{{value}}]','report':sources['report']},['report'])
    assert bundle.entries==('report',)
    with unittest.TestCase().assertRaises(TypeError):bundle.templates['row']='bad'

def test_tampered_unknown_duplicate_missing_and_loader_override_reject():
    "Verify tampered unknown duplicate missing and loader override reject."
    value=json.loads(make_bundle({'x':'good'},['x']));value['templates']['x']='bad'
    with unittest.TestCase().assertRaises(ValueError):load_bundle(json.dumps(value))
    with unittest.TestCase().assertRaises(ValueError):load_bundle('{"schema":1,"schema":1}')
    with unittest.TestCase().assertRaises(ValueError):make_bundle({'x':'x'},['missing'])
    bundle=load_bundle(make_bundle({'x':'x'},['x']))
    with unittest.TestCase().assertRaises(ValueError):bundle.environment(loader=None)

