"""显式映射进入真实csvcut管道，数据和原选列标识保持。"""
from io import StringIO
import csv,json
import pytest

def test_actual_cut_maps_before_output_after_original_selection(tmp_path):
    """仍按原列名选择，只改输出表头。@return None。"""
    from csvkit.utilities.csvcut import CSVCut
    path=tmp_path/'input.csv';path.write_text('城市,code\n杭州,001\n');output=StringIO()
    CSVCut(['-c','code,城市','--rename-columns-json',json.dumps({'城市':'city','code':'id'}),str(path)],output_file=output).run()
    assert list(csv.reader(StringIO(output.getvalue())))==[['id','city'],['001','杭州']]

def test_collisions_suffix_reserves_later_names():
    """自动后缀避开尚未遍历的真实目标名。@return None。"""
    from csvkit.headers import rename_columns
    with pytest.raises(ValueError):rename_columns(['a','b'],{'a':'b'})
    assert rename_columns(['a','b','b_2'],{'a':'b'},collision='suffix')==['b','b_3','b_2']

def test_unknown_ambiguous_empty_and_input_isolation():
    """未知、重复源和空目标不能静默漏改。@return None。"""
    from csvkit.headers import rename_columns
    for names,mapping in [(['a'],{'b':'x'}),(['a','a'],{'a':'x'}),(['a'],{'a':''})]:
        with pytest.raises(ValueError):rename_columns(names,mapping)
    names=['a'];mapping={'a':'x'};assert rename_columns(names,mapping)==['x'] and names==['a'] and mapping=={'a':'x'}
