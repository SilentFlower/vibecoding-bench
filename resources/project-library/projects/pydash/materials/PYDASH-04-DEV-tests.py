"Public regression tests for PYDASH-04-DEV; the complete business contract is in materials/PYDASH-04-DEV-contract.md."
import unittest
import pydash

def test_escaped_keys_arrays_and_root_replacement():
    "Verify escaped keys arrays and root replacement."
    source={'a/b':{'~key':[1,2]},'':3}
    assert pydash.get_pointer(source,'/a~1b/~0key/1')==2
    assert pydash.get_pointer(source,'/')==3 and pydash.get_pointer(source,'') is source
    assert pydash.set_pointer(source,'/a~1b/~0key/-',4) is source
    assert source['a/b']['~key']==[1,2,4]
    assert pydash.set_pointer(source,'',9)==9

def test_invalid_escapes_indices_and_noncontainers_do_not_mutate():
    "Verify invalid escapes indices and noncontainers do not mutate."
    source={'items':[1]}
    for pointer in ('items','/~2','/items/01','/items/-1','/items/4','/items/0/name'):
        with unittest.TestCase().assertRaises((ValueError,KeyError,IndexError,TypeError)):
            pydash.set_pointer(source,pointer,7)
        assert source=={'items':[1]}

