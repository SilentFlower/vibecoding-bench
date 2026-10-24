"""记录codec保留tuple键与有序反查，拒绝重复或未知格式。"""
import json
from bidict import bidict, OrderedBidict

def test_json_tuple_roundtrip():
    """标准JSON往返保留显式类型codec与关系顺序。@return None。"""
    from bidict.records import to_records, from_records
    source = OrderedBidict([(('a', 1), 2), (('b', 3), 4)])
    encoded = to_records(source, encode_key=list, encode_value=str)
    output = from_records(json.loads(json.dumps(encoded)), decode_key=tuple, decode_value=int, cls=OrderedBidict)
    assert list(output.items()) == list(source.items()) and output.inverse[4] == ('b', 3)

def test_duplicate_after_decode():
    """转换后键或值重复不能被构造器静默覆盖。@return None。"""
    import pytest
    from bidict.records import from_records
    document = {'schema': 1, 'codec': 'explicit-v1', 'pairs': [['1', 'a'], ['01', 'b']]}
    with pytest.raises(ValueError): from_records(document, decode_key=int, decode_value=str)

def test_schema_and_codec():
    """未知schema和codec明确拒绝。@return None。"""
    import pytest
    from bidict.records import from_records
    for document in [{'schema': 2, 'codec': 'explicit-v1', 'pairs': []}, {'schema': 1, 'codec': 'unknown', 'pairs': []}]:
        with pytest.raises(ValueError): from_records(document, decode_key=str, decode_value=str)
