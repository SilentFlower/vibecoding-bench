"Public regression tests for CSVKIT-O02-DEV; the complete business contract is in materials/CSVKIT-O02-DEV-contract.md."
import csv
from io import StringIO
from csvkit.utilities.csvgrep import CSVGrep

def run(tmp_path,contents,args):
    "Support the public regression through run."
    path=tmp_path/'input.csv';path.write_text(contents)
    output=StringIO();CSVGrep([*args,str(path)],output_file=output).run()
    return list(csv.reader(StringIO(output.getvalue())))

def test_unicode_substring_and_default_sensitive(tmp_path):
    "Verify unicode substring and default sensitive."
    data='name\nStraße\nOTHER\n'
    assert run(tmp_path,data,['-c','name','-m','STRASSE','--ignore-case'])==[['name'],['Straße']]
    assert run(tmp_path,data,['-c','name','-m','STRASSE'])==[['name']]

def test_matchfile_exact_inverse_and_short_rows(tmp_path):
    "Verify matchfile exact inverse and short rows."
    terms=tmp_path/'terms';terms.write_text('STRASSE\n')
    assert run(tmp_path,'a,b\n1,Straße\n2,else\n3\n',['-c','b','-f',str(terms),'--ignore-case','-i'])==[['a','b'],['2','else'],['3']]

def test_regex_flags_any_all_and_empty_pattern(tmp_path):
    "Verify regex flags any all and empty pattern."
    data='a,b\nYES,no\nno,YES\n'
    assert len(run(tmp_path,data,['-c','a,b','-r','^yes$','--ignore-case','-a']))==3
    assert run(tmp_path,data,['-c','a,b','-r','^yes$','--ignore-case'])==[['a','b']]
    assert len(run(tmp_path,data,['-c','a','-r','','--ignore-case']))==3
