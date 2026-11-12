"Public regression tests for STRUCTLOG-01-DEV; the complete business contract is in materials/STRUCTLOG-01-DEV-contract.md."
from structlog.processors import KeyValueRenderer,LogfmtRenderer

def test_both_renderers_keep_explicit_none_drop_only_absent():
    "Verify both renderers keep explicit none drop only absent."
    for sorted_keys in (False,True):
        values={'present':None,'false':False,'zero':0,'empty':''}
        text=KeyValueRenderer(key_order=['missing','present','false','zero','empty'],sort_keys=sorted_keys,drop_missing=True)(None,'info',dict(values))
        assert 'present=None' in text and 'missing=' not in text and 'false=False' in text and 'zero=0' in text
        text=LogfmtRenderer(key_order=['missing','present'],sort_keys=sorted_keys,drop_missing=True)(None,'info',dict(values))
        assert 'present=' in text and 'missing=' not in text

def test_default_missing_and_ordered_consumption_remain_compatible():
    "Verify default missing and ordered consumption remain compatible."
    values={'a':None,'b':2}
    result=KeyValueRenderer(key_order=['a','absent'],drop_missing=False)(None,'info',values)
    assert result=='a=None absent=None b=2' and values=={'b':2}

