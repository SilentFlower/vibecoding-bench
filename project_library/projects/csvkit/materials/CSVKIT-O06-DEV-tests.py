"Public regression tests for CSVKIT-O06-DEV; the complete business contract is in materials/CSVKIT-O06-DEV-contract.md."
import json
from io import StringIO

def test_single_pass_counts_bounded_samples_and_duplicates():
    "Verify single pass counts bounded samples and duplicates."
    from csvkit.utilities.csvfind import find_columns
    source=iter([['x','x'],['x','no'],['x']])
    report=find_columns(source,['same','same'],[0,1],value='x',sample_size=1)
    assert report['rows']==3 and [r['count'] for r in report['columns']]==[3,1]
    assert [r['sample_rows'] for r in report['columns']]==[[1],[1]] and list(source)==[]

def test_real_cli_json_logical_multiline_and_empty(tmp_path):
    "Verify real cli json logical multiline and empty."
    from csvkit.utilities.csvfind import CSVFind
    path=tmp_path/'data';path.write_text('a,b\n"hello\nworld",x\nx,x\n');out=StringIO()
    CSVFind(['--value','x','--json',str(path)],output_file=out).run()
    report=json.loads(out.getvalue());assert report['rows']==2 and report['columns'][1]['sample_rows']==[1,2]

def test_empty_cells_short_rows_regex_and_budget():
    "Verify empty cells short rows regex and budget."
    from csvkit.utilities.csvfind import find_columns
    import pytest
    assert find_columns(iter([['a'],['b','']]),['a','b'],[1],value='',sample_size=0)['columns'][0]['count']==2
    assert find_columns(iter([['Ab'],['no']]),['a'],[0],regex='(?i)^ab$')['columns'][0]['count']==1
    with pytest.raises(ValueError):find_columns(iter([]),['x'],[0],value='x',sample_size=-1)
