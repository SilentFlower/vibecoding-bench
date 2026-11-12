"Public regression tests for BO-JSONL-WRITER-DEV; the complete business contract is in materials/BO-JSONL-WRITER-DEV-contract.md."
from io import StringIO,BytesIO
import json
import pytest
from boltons.jsonutils import JSONLWriter,JSONLIterator

def test_text_and_binary_roundtrip_through_actual_reader():
    stream=StringIO();writer=JSONLWriter(stream)
    assert writer.write_many([{'a':1},['雪',2]])==2 and writer.count==2
    stream.seek(0);assert list(JSONLIterator(stream))==[{'a':1},['雪',2]]
    binary=BytesIO();JSONLWriter(binary,binary=True).write({'雪':'花'})
    assert json.loads(binary.getvalue())=={'雪':'花'}

def test_failed_serialization_does_not_write_or_increment_count():
    stream=StringIO();writer=JSONLWriter(stream);writer.write(1);before=stream.getvalue()
    with pytest.raises(TypeError):
        writer.write(object())
    assert stream.getvalue()==before and writer.count==1

def test_multiline_and_invalid_custom_results_are_rejected_before_write():
    for result in ('{}\n{}','not json',b'{}'):
        stream=StringIO();writer=JSONLWriter(stream,dumps=lambda value:result)
        with pytest.raises((ValueError,TypeError)):
            writer.write(1)
        assert stream.getvalue()=='' and writer.count==0

def test_lazy_input_failure_preserves_prior_records_and_stream_ownership():
    stream=StringIO();writer=JSONLWriter(stream)
    def values():
        yield 1
        raise LookupError('synthetic')
    with pytest.raises(LookupError):
        writer.write_many(values())
    writer.flush()
    assert stream.getvalue()=='1\n' and writer.count==1 and not stream.closed
