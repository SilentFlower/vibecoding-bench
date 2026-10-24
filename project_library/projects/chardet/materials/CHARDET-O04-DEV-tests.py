"Public regression tests for CHARDET-O04-DEV; the complete business contract is in materials/CHARDET-O04-DEV-contract.md."
def test_ids_local_errors_and_duplicate_ids():
    "Verify ids local errors and duplicate ids."
    from chardet.batch import detect_many
    rows = list(detect_many([('same', b'abc'), ('bad', 'text'), ('same', b'def')]))
    assert [row['id'] for row in rows] == ['same', 'bad', 'same']
    assert rows[0]['result']['encoding'] == 'ascii' and rows[1]['result'] is None and rows[2]['error'] is None

def test_lazy_and_stop():
    "Verify lazy and stop."
    from chardet.batch import detect_many
    source = iter([('one', b'abc'), ('bad', 3), ('tail', b'x')])
    rows = detect_many(source, on_error='stop')
    assert next(rows)['id'] == 'one'
    assert len(list(rows)) == 1 and next(source)[0] == 'tail'

def test_raise_and_input_shape():
    "Verify raise and input shape."
    import pytest
    from chardet.batch import detect_many
    with pytest.raises(TypeError): list(detect_many([('x', 3)], on_error='raise'))
    with pytest.raises(TypeError): list(detect_many(b'not records'))
