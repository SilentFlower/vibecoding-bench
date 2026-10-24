"Public regression tests for TB-INDEX-DEV; the complete business contract is in materials/TB-INDEX-DEV-contract.md."
import pytest
from tabulate import tabulate,SEPARATING_LINE

def test_sized_indices_count_only_business_rows():
    rows=[['a'],SEPARATING_LINE,['b']]
    result=tabulate(rows,showindex=['first','second'],tablefmt='grid')
    assert 'first' in result and 'second' in result

def test_list_tuple_and_iterator_indices_render_equally():
    rows=[['a'],SEPARATING_LINE,['b']]
    values=['one','two']
    assert tabulate(rows,showindex=values)==tabulate(rows,showindex=tuple(values))==tabulate(rows,showindex=iter(values))
    assert values==['one','two']

def test_wrong_business_index_count_is_rejected():
    with pytest.raises(ValueError):
        tabulate([['a'],SEPARATING_LINE,['b']],showindex=['one','two','extra'])

def test_empty_and_separator_only_tables_do_not_consume_indices():
    assert tabulate([],showindex=[])==''
    assert tabulate([SEPARATING_LINE],showindex=[])==tabulate([SEPARATING_LINE],showindex=iter([]))
