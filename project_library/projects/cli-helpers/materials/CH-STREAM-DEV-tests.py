"Public regression tests for CH-STREAM-DEV; the complete business contract is in materials/CH-STREAM-DEV-contract.md."
import json
import pytest
from cli_helpers.tabular_output import TabularOutputFormatter

def test_json_lines_do_not_prefetch_next_rows():
    seen=[]
    def rows():
        for value in range(3):
            seen.append(value)
            yield [value]
    output=TabularOutputFormatter('jsonl').stream_output(rows(),['n'],column_types=[int])
    assert seen==[] and json.loads(next(output))=={'n':0} and seen==[0]
    output.close()
    assert seen==[0]

def test_csv_header_does_not_consume_a_data_row():
    seen=[]
    def rows():
        seen.append(1)
        yield ['a,b']
    output=TabularOutputFormatter('csv').stream_output(rows(),['name'],column_types=[str])
    assert next(output)=='name' and seen==[]
    assert next(output)=='"a,b"' and seen==[1]

def test_explicit_column_types_and_supported_format_are_required():
    formatter=TabularOutputFormatter('jsonl')
    with pytest.raises(ValueError):
        formatter.stream_output([],['n'])
    with pytest.raises(ValueError):
        formatter.stream_output([],['n'],column_types=[])
    with pytest.raises(ValueError):
        formatter.stream_output([],['n'],format_name='simple',column_types=[int])

def test_late_row_error_propagates_after_already_yielded_rows():
    def rows():
        yield [1]
        raise LookupError('synthetic')
    output=TabularOutputFormatter('jsonl').stream_output(rows(),['n'],column_types=[int])
    assert json.loads(next(output))=={'n':1}
    with pytest.raises(LookupError):
        next(output)
