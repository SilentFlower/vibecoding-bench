"Public regression tests for STRUCTLOG-03-DEV; the complete business contract is in materials/STRUCTLOG-03-DEV-contract.md."
import unittest
from structlog.processors import FieldRenamer

def test_swap_chain_and_missing_sources_preserve_values():
    "Verify swap chain and missing sources preserve values."
    payload=[];source={'a':payload,'b':2,'other':3}
    result=FieldRenamer({'a':'b','b':'c','missing':'z'})(None,'info',source)
    assert result=={'b':payload,'c':2,'other':3} and result['b'] is payload
    assert source=={'a':payload,'b':2,'other':3}
    assert FieldRenamer({'a':'b','b':'a'})(None,'info',source)=={'a':2,'b':payload,'other':3}

def test_error_keep_overwrite_and_dependent_keep_are_atomic():
    "Verify error keep overwrite and dependent keep are atomic."
    source={'a':1,'b':2,'c':3}
    with unittest.TestCase().assertRaises(ValueError):FieldRenamer({'a':'b'})(None,'info',source)
    assert FieldRenamer({'a':'b','b':'c'},conflict='keep')(None,'info',source)==source
    assert FieldRenamer({'a':'b'},conflict='overwrite')(None,'info',source)=={'b':1,'c':3}
    with unittest.TestCase().assertRaises(ValueError):FieldRenamer({'a':'x','b':'x'})

