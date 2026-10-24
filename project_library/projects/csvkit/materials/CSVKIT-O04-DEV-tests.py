"Public regression tests for CSVKIT-O04-DEV; the complete business contract is in materials/CSVKIT-O04-DEV-contract.md."
from io import StringIO
import csv
import pytest

def run(tmp_path,text,args):
    "Support the public regression through run."
    from csvkit.utilities.csvslice import CSVSlice
    path=tmp_path/'input.csv';path.write_text(text);output=StringIO();CSVSlice([*args,str(path)],output_file=output).run()
    return list(csv.reader(StringIO(output.getvalue())))

def test_logical_multiline_slice_and_step(tmp_path):
    "Verify logical multiline slice and step."
    text='id,note\n1,"a\nb"\n2,c\n3,d\n4,e\n'
    assert run(tmp_path,text,['--start','0','--stop','3','--step','2'])==[['id','note'],['1','a\nb'],['3','d']]

def test_tail_zero_header_only_and_empty(tmp_path):
    "Verify tail zero header only and empty."
    assert run(tmp_path,'id\n1\n2\n3\n',['--tail','2'])==[['id'],['2'],['3']]
    assert run(tmp_path,'id\n1\n',['--tail','0'])==[['id']]
    assert run(tmp_path,'id\n',[])==[['id']] and run(tmp_path,'',[])==[]

def test_invalid_modes_and_headerless(tmp_path):
    "Verify invalid modes and headerless."
    for args in [['--step','0'],['--start','-1'],['--tail','2','--stop','3']]:
        with pytest.raises(SystemExit):run(tmp_path,'a\n1\n',args)
    assert run(tmp_path,'1,2\n3,4\n',['-H','--stop','1'])==[['a','b'],['1','2']]
