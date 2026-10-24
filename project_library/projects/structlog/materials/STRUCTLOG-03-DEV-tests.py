"""批量改名按原快照而非连续覆盖。"""
import unittest
from structlog.processors import FieldRenamer

def test_swap_chain_and_missing_sources_preserve_values():
    """互换与a到b到c保留各自业务值。@return None。"""
    payload=[];source={'a':payload,'b':2,'other':3}
    result=FieldRenamer({'a':'b','b':'c','missing':'z'})(None,'info',source)
    assert result=={'b':payload,'c':2,'other':3} and result['b'] is payload
    assert source=={'a':payload,'b':2,'other':3}
    assert FieldRenamer({'a':'b','b':'a'})(None,'info',source)=={'a':2,'b':payload,'other':3}

def test_error_keep_overwrite_and_dependent_keep_are_atomic():
    """keep不能让间接冲突丢掉本应保留的源值。@return None。"""
    source={'a':1,'b':2,'c':3}
    with unittest.TestCase().assertRaises(ValueError):FieldRenamer({'a':'b'})(None,'info',source)
    assert FieldRenamer({'a':'b','b':'c'},conflict='keep')(None,'info',source)==source
    assert FieldRenamer({'a':'b'},conflict='overwrite')(None,'info',source)=={'b':1,'c':3}
    with unittest.TestCase().assertRaises(ValueError):FieldRenamer({'a':'x','b':'x'})

