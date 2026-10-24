"Public regression tests for FT-PIPELINE-DEV; the complete business contract is in materials/FT-PIPELINE-DEV-contract.md."
import pytest
from ftfy import TextFixerConfig,apply_plan
from ftfy.pipeline import TextRepairPipeline

def test_real_changes_include_replayable_audit_and_preserve_input():
    original={'name':'cafÃ©','raw':'cafÃ©'};result=TextRepairPipeline([('name',)]).process(original)
    assert result.value=={'name':'café','raw':'cafÃ©'} and original['name']=='cafÃ©'
    path,audit=result.changes[0];assert path==('name',) and apply_plan(original['name'],list(audit.explanation))=='café'

def test_collect_continues_and_keeps_input_indices():
    result=list(TextRepairPipeline([('name',)]).run([{'name':'ﬁ'},{'name':4},{'name':'ok'}],errors='collect'))
    assert [(row.index,row.status) for row in result]==[(0,'passed'),(1,'error'),(2,'passed')]
    assert result[1].error[0]=='TypeError' and result[2].changes==()

def test_pipeline_is_lazy_and_reusable_without_record_state():
    calls=[]
    def source(): calls.append(1);yield {'name':'ﬁ'}
    pipeline=TextRepairPipeline([('name',)]);stream=pipeline.run(source());assert calls==[]
    assert next(stream).value['name']=='fi' and pipeline.process({'name':'ok'}).changes==()

def test_disabled_explanation_policy_and_missing_skip_are_retained():
    pipeline=TextRepairPipeline([('name',)],TextFixerConfig(explain=False,fix_latin_ligatures=False),missing='skip')
    assert pipeline.process({'name':'ﬁ'}).changes==() and pipeline.process({}).value=={}
    with pytest.raises(ValueError): pipeline.run([],errors='skip')
