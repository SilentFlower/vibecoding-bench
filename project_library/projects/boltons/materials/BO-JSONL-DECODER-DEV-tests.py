"Public regression tests for BO-JSONL-DECODER-DEV; the complete business contract is in materials/BO-JSONL-DECODER-DEV-contract.md."
from io import StringIO,BytesIO
from decimal import Decimal
import json
import pytest
from boltons.jsonutils import JSONLIterator

def test_decimal_and_object_pairs_hooks_are_preserved():
    rows=list(JSONLIterator(StringIO('{"a":1.20}\n'),loads=lambda line:json.loads(line,parse_float=Decimal)))
    assert rows==[{'a':Decimal('1.20')}]
    rows=list(JSONLIterator(StringIO('{"a":1,"a":2}\n'),loads=lambda line:json.loads(line,object_pairs_hook=list)))
    assert rows==[[('a',1),('a',2)]]

def test_blank_lines_skip_decoder_and_return_identity_is_preserved():
    seen=[];result=object()
    def decoder(line):
        seen.append(line)
        return result
    iterator=JSONLIterator(StringIO('\n  \n{}\n'),loads=decoder)
    assert next(iterator) is result and len(seen)==1

def test_reverse_and_ignore_errors_keep_existing_behavior():
    stream=BytesIO(b'1\nbad\n2\n')
    assert list(JSONLIterator(stream,reverse=True,ignore_errors=True,loads=json.loads))==[2,1]

def test_invalid_decoder_is_rejected_before_seek_or_read():
    class Stream:
        def read(self,*args):
            raise AssertionError('不应读取')
        def seek(self,*args):
            raise AssertionError('不应定位')
    with pytest.raises(TypeError):
        JSONLIterator(Stream(),loads=3,reverse=True)
