"Public regression tests for PYTHON-LIQUID-04-DEV; the complete business contract is in materials/PYTHON-LIQUID-04-DEV-contract.md."
import asyncio
import unittest
from liquid import Environment,StrictUndefined
from liquid.record_rendering import render_records,render_records_async

def test_ordered_results_failure_and_assign_context_isolation():
    "Verify ordered results failure and assign context isolation."
    template=Environment(undefined=StrictUndefined).from_string('{% if set_flag %}{% assign x = "local" %}{% endif %}{{x}}')
    rows=[('one',{'set_flag':True}),('two',{'set_flag':False}),('three',{'set_flag':False,'x':'given'})]
    results=list(render_records(template,rows))
    assert [(r.record_id,r.status,r.output) for r in results]==[('one','rendered','local'),('two','failed',None),('three','rendered','given')]
    assert results[1].error=='UndefinedError'

def test_async_matches_sync_failfast_duplicate_and_early_close():
    "Verify async matches sync failfast duplicate and early close."
    template=Environment(undefined=StrictUndefined).from_string('{{value}}')
    rows=[('a',{'value':1}),('b',{}),('c',{'value':3})]
    async def run():
        actual=[item async for item in render_records_async(template,rows)]
        assert actual==list(render_records(template,rows))
        seen=[]
        def source():
            for n in range(4):seen.append(n);yield (n,{'value':n})
        iterator=render_records_async(template,source());first=await anext(iterator);await iterator.aclose()
        assert first.output=='0' and seen==[0]
    asyncio.run(run())
    with unittest.TestCase().assertRaises(Exception):list(render_records(template,rows,continue_on_error=False))
    with unittest.TestCase().assertRaises(ValueError):list(render_records(template,[('a',{'value':1}),('a',{'value':2})]))

