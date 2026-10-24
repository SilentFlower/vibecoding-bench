"Public regression tests for DEEPDIFF-O06-DEV; the complete business contract is in materials/DEEPDIFF-O06-DEV-contract.md."
from deepdiff import DeepDiff,Delta
import json
import pytest

def test_changed_path_preserved_values_hidden_and_delta_unchanged():
    "Verify changed path preserved values hidden and delta unchanged."
    from deepdiff.reporting import redacted_report
    a={'token':'secret-old','qty':1};b={'token':'secret-new','qty':2};diff=DeepDiff(a,b)
    report=redacted_report(diff,redact_paths=["root['token']"],left_label='api',right_label='device')
    text=json.dumps(report);assert 'secret' not in text and "root['token']" in text and report['labels']['left']=='api'
    assert report['changes']['values_changed']["root['qty']"]['new_value']==2
    assert a+Delta(diff)==b and diff['values_changed']["root['token']"]['old_value']=='secret-old'

def test_parent_wildcards_literal_star_and_coarse_subtree():
    "Verify parent wildcards literal star and coarse subtree."
    from deepdiff.reporting import redacted_report
    a={'users':[{'token':'one','name':'a'}],'*':'literal','keep':'plain'};b={'users':[{'token':'two','name':'b'}],'*':'next','keep':'later'}
    report=redacted_report(DeepDiff(a,b,view='tree'),redact_paths=["root['users'][*]['token']","root['*']"])
    assert 'one' not in json.dumps(report) and 'two' not in json.dumps(report) and 'plain' in json.dumps(report)
    report=redacted_report(DeepDiff({'a':{'token':'secret-before'}},{'a':{'token':'secret-after','other':1}},threshold_to_diff_deeper=1),redact_paths=["root['a']['token']"])
    assert 'secret-before' not in json.dumps(report) and 'secret-after' not in json.dumps(report)

def test_serialization_after_mask_and_bad_configuration():
    "Verify serialization after mask and bad configuration."
    from deepdiff.reporting import redacted_report
    class Secret:
        "Public regression fixture: Secret."
    called=[];diff=DeepDiff({'x':Secret()},{'x':'new-secret'})
    result=redacted_report(diff,redact_paths=["root['x']"],default_mapping={Secret:lambda x:called.append(x) or 'leak'})
    assert called==[] and 'new-secret' not in json.dumps(result)
    with pytest.raises(ValueError):redacted_report(diff,left_label='same',right_label='same')
    with pytest.raises(ValueError):redacted_report(diff,redact_paths=['not-root'])
