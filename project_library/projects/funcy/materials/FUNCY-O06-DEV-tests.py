"Public regression tests for FUNCY-O06-DEV; the complete business contract is in materials/FUNCY-O06-DEV-contract.md."
import pytest

def test_three_real_stages_adapters_and_optional_report():
    "Verify three real stages adapters and optional report."
    from funcy.pipeline import Pipeline,Stage
    events=[]
    p=Pipeline([Stage('parse',lambda text:int(text),input_adapter=str.strip),Stage('scale',lambda value:value*2),Stage('check',lambda value:events.append(value) or value,output_adapter=str)])
    assert p(' 3 ')=='6' and events==[6]
    report=p.run('4',report=True);assert report.ok and report.value=='8' and [e['stage'] for e in report.events]==['parse','scale','check']

def test_failure_context_cause_report_and_no_later_stage():
    "Verify failure context cause report and no later stage."
    from funcy.pipeline import Pipeline,Stage,PipelineStageError
    original=ValueError('secret-input');calls=[]
    def fail(value):raise original
    p=Pipeline([Stage('bad',fail),Stage('later',lambda x:calls.append(x))])
    with pytest.raises(PipelineStageError) as error:p('secret')
    assert error.value.stage=='bad' and error.value.__cause__ is original and calls==[] and 'secret' not in str(error.value)
    report=Pipeline([Stage('bad',fail)],on_error='report')('secret')
    assert not report.ok and report.failed_stage=='bad' and report.events[0]['error_kind']=='ValueError'

def test_empty_identity_selector_and_invalid_stage_config():
    "Verify empty identity selector and invalid stage config."
    from funcy.pipeline import Pipeline,Stage
    value=object();assert Pipeline([])(value) is value
    assert Pipeline([Stage('first',0)])([3,4])==3
    with pytest.raises(ValueError):Pipeline([Stage('same',lambda x:x),Stage('same',lambda x:x)])
    with pytest.raises(TypeError):Pipeline([Stage('bad',lambda x:x,input_adapter=3)])
    async def adapter(value):return value
    with pytest.raises(TypeError):Pipeline([Stage('bad',lambda x:x,output_adapter=adapter)])
    from funcy.pipeline import PipelineStageError
    coroutine=adapter(1)
    with pytest.raises(PipelineStageError):Pipeline([Stage('bad',lambda x:x,output_adapter=lambda value:coroutine)])(1)
    assert coroutine.cr_frame is None
