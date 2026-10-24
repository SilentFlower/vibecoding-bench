"""临时sink拥有严格作用域，只关闭自己的资源。"""
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    """取得独立logger。@return Logger。"""
    logger.remove();log=deepcopy(logger);log.remove();return log

def test_scope_only_removes_owned_sink_and_nested_exits():
    """外部sink持续收取，嵌套只关闭自己的id。@return None。"""
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
    """业务异常不丢，外部提前移除可重复退出，调用方流仍可用。@return None。"""
    import io
    log=clean();stream=io.StringIO();error=LookupError('body')
    with pytest.raises(LookupError) as caught:
        with log.sink_context(stream,format='{message}') as identifier:
            log.info('inside');log.remove(identifier);raise error
    assert caught.value is error and not stream.closed and stream.getvalue()=='inside\n'

def test_queued_records_finish_and_cleanup_failure_does_not_mask_body():
    """原队列关闭协议完成已有记录；stop故障不能掩盖原业务异常。@return None。"""
    log=clean();messages=[]
    with log.sink_context(messages.append,format='{message}',enqueue=True):
        log.info('a');log.info('b')
    assert ''.join(messages)=='a\nb\n'
    class Broken:
        """可受控失败的真实流协议。"""
        def write(self,message):pass
        def stop(self):raise RuntimeError('close failed')
    error=ValueError('body')
    with pytest.warns(RuntimeWarning):
        with pytest.raises(ValueError) as caught:
            with log.sink_context(Broken()):raise error
    assert caught.value is error
