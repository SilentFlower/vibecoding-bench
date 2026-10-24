"""复用重试装饰器时，每个目标拥有独立日志和回调集合。"""
import asyncio
import logging
import pytest
import backoff


def test_reuse_exception_decorator(caplog):
    """三次装饰分别只记录一次放弃日志。@return None。"""
    calls = []
    decorate = backoff.on_exception(backoff.constant, ValueError, max_tries=1,
        logger='development.reuse', on_giveup=calls.append)
    def fail():
        """产生真实业务异常。@return 不返回。"""
        raise ValueError('target')
    with caplog.at_level(logging.ERROR, logger='development.reuse'):
        for _ in range(3):
            caplog.clear()
            with pytest.raises(ValueError):
                decorate(fail)()
            assert len(caplog.records) == 1
    assert len(calls) == 3


def test_reuse_predicate_and_generator_handlers(caplog):
    """一次性用户处理器也可在每个目标上恰好执行一次。@return None。"""
    calls = []
    decorate = backoff.on_predicate(backoff.constant, max_tries=1,
        logger='development.predicate', on_giveup=(h for h in [calls.append]))
    with caplog.at_level(logging.ERROR, logger='development.predicate'):
        for _ in range(3):
            caplog.clear()
            assert decorate(lambda: False)() is False
            assert len(caplog.records) == 1
    assert len(calls) == 3


def test_reuse_mixed_sync_async(caplog):
    """同一工厂装饰同步和异步函数不相互积累默认日志。@return None。"""
    decorate = backoff.on_predicate(backoff.constant, max_tries=1, logger='development.mixed')
    async def target():
        """返回需要放弃的值。@return False。"""
        return False
    with caplog.at_level(logging.ERROR, logger='development.mixed'):
        decorate(lambda: False)()
        caplog.clear()
        assert asyncio.run(decorate(target)()) is False
        assert len(caplog.records) == 1
