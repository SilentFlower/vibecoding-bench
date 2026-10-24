"""TSV/自动路径真正把多余字段策略传到最内层CSV reader。"""
import io
import unittest
from sqlite_utils.utils import rows_from_file,Format,RowError

def test_tsv_collect_ignore_and_default_error_match_csv():
    """额外字段先被内层报错后外层无法补救，必须正确传递。@return None。"""
    for delimiter,format in ((',',Format.CSV),('\t',Format.TSV)):
        raw=f'a{delimiter}b\n1{delimiter}2{delimiter}3\n'.encode()
        rows,_=rows_from_file(io.BytesIO(raw),format=format,extras_key='rest')
        assert list(rows)==[{'a':'1','b':'2','rest':['3']}]
        rows,_=rows_from_file(io.BytesIO(raw),format=format,ignore_extras=True)
        assert list(rows)==[{'a':'1','b':'2'}]
        rows,_=rows_from_file(io.BytesIO(raw),format=format)
        with unittest.TestCase().assertRaises(RowError):list(rows)

def test_detected_delimiter_policy_short_rows_and_conflicting_options():
    """自动探测样本有足够正常行，避免把嗅探问题冒充策略失败。@return None。"""
    raw=('a\tb\n'+''.join('1\t2\n' for _ in range(30))+'3\t4\textra\n').encode()
    rows,format=rows_from_file(io.BytesIO(raw),extras_key='remaining')
    values=list(rows);assert values[-1]=={'a':'3','b':'4','remaining':['extra']} and format is Format.TSV
    rows,_=rows_from_file(io.BytesIO(b'a\tb\n1\n'),format=Format.TSV,ignore_extras=True)
    assert list(rows)==[{'a':'1','b':None}]
    with unittest.TestCase().assertRaises(ValueError):rows_from_file(io.BytesIO(raw),ignore_extras=True,extras_key='x')

