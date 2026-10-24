"""JSON路径必须显式，普通属性解析和点路径保持原样。"""
import unittest
import pydash

def test_escaped_keys_arrays_and_root_replacement():
    """斜杠、波浪号和空键按RFC顺序解码。@return None。"""
    source={'a/b':{'~key':[1,2]},'':3}
    assert pydash.get_pointer(source,'/a~1b/~0key/1')==2
    assert pydash.get_pointer(source,'/')==3 and pydash.get_pointer(source,'') is source
    assert pydash.set_pointer(source,'/a~1b/~0key/-',4) is source
    assert source['a/b']['~key']==[1,2,4]
    assert pydash.set_pointer(source,'',9)==9

def test_invalid_escapes_indices_and_noncontainers_do_not_mutate():
    """不借用负索引、前导零或任意getattr。@return None。"""
    source={'items':[1]}
    for pointer in ('items','/~2','/items/01','/items/-1','/items/4','/items/0/name'):
        with unittest.TestCase().assertRaises((ValueError,KeyError,IndexError,TypeError)):
            pydash.set_pointer(source,pointer,7)
        assert source=={'items':[1]}

