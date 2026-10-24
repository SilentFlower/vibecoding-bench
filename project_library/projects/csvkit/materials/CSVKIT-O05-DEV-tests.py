"Public regression tests for CSVKIT-O05-DEV; the complete business contract is in materials/CSVKIT-O05-DEV-contract.md."
from io import StringIO
import csv,json
import pytest

def test_actual_cut_maps_before_output_after_original_selection(tmp_path):
    "Verify actual cut maps before output after original selection."
    from csvkit.utilities.csvcut import CSVCut
    path=tmp_path/'input.csv';path.write_text('城市,code\n杭州,001\n');output=StringIO()
    CSVCut(['-c','code,城市','--rename-columns-json',json.dumps({'城市':'city','code':'id'}),str(path)],output_file=output).run()
    assert list(csv.reader(StringIO(output.getvalue())))==[['id','city'],['001','杭州']]

def test_collisions_suffix_reserves_later_names():
    "Verify collisions suffix reserves later names."
    from csvkit.headers import rename_columns
    with pytest.raises(ValueError):rename_columns(['a','b'],{'a':'b'})
    assert rename_columns(['a','b','b_2'],{'a':'b'},collision='suffix')==['b','b_3','b_2']

def test_unknown_ambiguous_empty_and_input_isolation():
    "Verify unknown ambiguous empty and input isolation."
    from csvkit.headers import rename_columns
    for names,mapping in [(['a'],{'b':'x'}),(['a','a'],{'a':'x'}),(['a'],{'a':''})]:
        with pytest.raises(ValueError):rename_columns(names,mapping)
    names=['a'];mapping={'a':'x'};assert rename_columns(names,mapping)==['x'] and names==['a'] and mapping=={'a':'x'}
