"""批检测保留标识和顺序，坏记录后可恢复。"""
def test_ids_local_errors_and_duplicate_ids():
    """重复id不丢记录，非法载荷只是局部失败。@return None。"""
    from chardet.batch import detect_many
    rows = list(detect_many([('same', b'abc'), ('bad', 'text'), ('same', b'def')]))
    assert [row['id'] for row in rows] == ['same', 'bad', 'same']
    assert rows[0]['result']['encoding'] == 'ascii' and rows[1]['result'] is None and rows[2]['error'] is None

def test_lazy_and_stop():
    """首条只消费首条，stop不执行尾部。@return None。"""
    from chardet.batch import detect_many
    source = iter([('one', b'abc'), ('bad', 3), ('tail', b'x')])
    rows = detect_many(source, on_error='stop')
    assert next(rows)['id'] == 'one'
    assert len(list(rows)) == 1 and next(source)[0] == 'tail'

def test_raise_and_input_shape():
    """fail-fast和整bytes误用明确失败。@return None。"""
    import pytest
    from chardet.batch import detect_many
    with pytest.raises(TypeError): list(detect_many([('x', 3)], on_error='raise'))
    with pytest.raises(TypeError): list(detect_many(b'not records'))
