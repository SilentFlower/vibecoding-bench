"""公开JSON Lines真实流回归。"""
from io import StringIO
import pytest
from simplejson.lines import iterloads,iterdumps,dump

def test_mixed_bytes_bom_blank_and_physical_error_line():
    result=list(iterloads([b'\xef\xbb\xbf{"v":1}\r\n','\n','{"a":1,"a":2}\n','false\n'],errors='collect'))
    assert [(row.line,row.status) for row in result]==[(1,'passed'),(3,'error'),(4,'passed')]
    assert result[2].value is False

def test_reader_and_writer_are_lazy_and_keep_one_record_per_line():
    calls=[]
    def source():
        for value in (1,2): calls.append(value);yield str(value)
    reader=iterloads(source());assert calls==[] and next(reader)==1 and calls==[1]
    assert list(iterdumps([{'b':2,'a':1},None]))==['{"a":1,"b":2}\n','null\n']

def test_limit_and_raise_line_are_explicit():
    with pytest.raises(ValueError,match='2'): list(iterloads(['1\n','1234\n'],max_chars=3))
    with pytest.raises(ValueError): iterloads(iter([]),errors='skip')

def test_bad_record_never_writes_its_partial_json():
    stream=StringIO()
    with pytest.raises(TypeError): dump([{'ok':1},{'bad':set([1])}],stream)
    assert stream.getvalue()=='{"ok":1}\n'
