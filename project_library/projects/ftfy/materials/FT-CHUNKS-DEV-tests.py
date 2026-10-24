"""公开分块文本修复回归。"""
from io import StringIO
import pytest
from ftfy import fix_file,TextFixerConfig
from ftfy.streaming import fix_chunks

def test_every_split_matches_actual_file_semantics():
    text='cafÃ©\r\nnext ﬁ\nlast'
    expected=list(fix_file(StringIO(text)))
    for index in range(len(text)+1): assert list(fix_chunks([text[:index],text[index:]]))==expected

def test_auto_html_policy_is_retained_across_lines():
    text='<tag>&amp;</tag>\n&amp;\n'
    assert list(fix_chunks(['<tag>','&amp;</tag>\n&','amp;\n']))==list(fix_file(StringIO(text)))

def test_stream_is_lazy_and_final_unterminated_line_survives():
    calls=[]
    def source():
        calls.append(1);yield 'a\n'
        calls.append(2);yield 'cafÃ©'
    stream=fix_chunks(source());assert calls==[] and next(stream)=='a\n' and calls==[1]
    assert list(stream)==['café']

def test_budget_and_invalid_chunks_fail_explicitly():
    with pytest.raises(ValueError): fix_chunks([],max_line_length=0)
    with pytest.raises(ValueError): list(fix_chunks(['abc','de'],max_line_length=4))
    with pytest.raises(TypeError): list(fix_chunks([b'bad']))
