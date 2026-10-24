"""日志名称不可掩盖可调用实例和partial的真实业务异常。"""
from functools import partial
import logging
import pytest
import backoff


def test_partial_preserves_error(caplog):
    """绑定实参不进入日志，原异常对象保持。@return None。"""
    error = ValueError('target')
    def fail(secret):
        """抛出业务异常。@param secret 合成绑定实参。@return 不返回。"""
        raise error
    target = backoff.on_exception(backoff.constant, ValueError, max_tries=1)(partial(fail, 'hidden-token'))
    with caplog.at_level(logging.ERROR, logger='backoff'):
        with pytest.raises(ValueError) as result:
            target()
    assert result.value is error
    assert 'fail' in caplog.text and 'hidden-token' not in caplog.text


def test_callable_instance(caplog):
    """无__name__目标使用类型名。@return None。"""
    class Endpoint:
        """返回重试失败值的业务目标。"""
        def __call__(self):
            """返回0。@return 0。"""
            return 0
    with caplog.at_level(logging.ERROR, logger='backoff'):
        assert backoff.on_predicate(backoff.constant, max_tries=1)(Endpoint())() == 0
    assert 'Endpoint' in caplog.text


def test_logger_none_unchanged():
    """禁用日志仍直接返回真实结果。@return None。"""
    assert backoff.on_predicate(backoff.constant, max_tries=1, logger=None)(partial(lambda x: x, 8))() == 8
