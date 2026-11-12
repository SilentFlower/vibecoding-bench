"Public regression tests for LOGURU-O02-DEV; the complete business contract is in materials/LOGURU-O02-DEV-contract.md."
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    "Support the public regression through clean."
    logger.remove();log=deepcopy(logger);log.remove();return log

def test_scope_only_removes_owned_sink_and_nested_exits():
    "Verify scope only removes owned sink and nested exits."
    log=clean();outer=[];first=[];second=[];log.add(outer.append,format='{message}')
    with log.sink_context(first.append,format='{message}') as identifier:
        log.info('one')
        with log.sink_context(second.append,format='{message}'):log.info('two')
        log.info('three')
    log.info('four')
    assert ''.join(first)=='one\ntwo\nthree\n' and ''.join(second)=='two\n'
    assert ''.join(outer)=='one\ntwo\nthree\nfour\n'
    with pytest.raises(ValueError):log.remove(identifier)
    log.remove()

def test_exception_early_remove_and_caller_owned_stream():
    "Verify exception early remove and caller owned stream."
    import io
    log=clean();stream=io.StringIO();error=LookupError('body')
    with pytest.raises(LookupError) as caught:
        with log.sink_context(stream,format='{message}') as identifier:
            log.info('inside');log.remove(identifier);raise error
    assert caught.value is error and not stream.closed and stream.getvalue()=='inside\n'

def test_queued_records_finish_and_cleanup_failure_does_not_mask_body():
    "Verify queued records finish and cleanup failure does not mask body."
    log=clean();messages=[]
    with log.sink_context(messages.append,format='{message}',enqueue=True):
        log.info('a');log.info('b')
    assert ''.join(messages)=='a\nb\n'
    class Broken:
        "Public regression fixture: Broken."
        def write(self,message):pass
        def stop(self):raise RuntimeError('close failed')
    error=ValueError('body')
    with pytest.warns(RuntimeWarning):
        with pytest.raises(ValueError) as caught:
            with log.sink_context(Broken()):raise error
    assert caught.value is error
