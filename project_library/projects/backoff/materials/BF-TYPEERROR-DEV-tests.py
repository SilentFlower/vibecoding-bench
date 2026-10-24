"""动态配置和jitter自己的TypeError不能被误当旧签名。"""
import pytest
import backoff


def test_dynamic_configuration_typeerror():
    """配置失败时不得运行真实目标。@return None。"""
    calls = []
    failure = TypeError('config body')
    def broken():
        """配置内部错误。@return 不返回。"""
        raise failure
    target = backoff.on_predicate(backoff.constant, max_tries=broken, logger=None)(lambda: calls.append(1) or 3)
    with pytest.raises(TypeError) as result:
        target()
    assert result.value is failure and calls == []


def test_jitter_body_typeerror():
    """合法一参jitter内部错误原样传播，不能再次零参调用。@return None。"""
    calls = []
    failure = TypeError('jitter body')
    def jitter(value):
        """模拟抖动内部错误。@param value 等待时间。@return 不返回。"""
        calls.append(value)
        raise failure
    target = backoff.on_predicate(backoff.constant, interval=0, max_tries=2, jitter=jitter, logger=None)(lambda: False)
    with pytest.raises(TypeError) as result:
        target()
    assert result.value is failure and calls == [0]


def test_legacy_jitter_and_runtime():
    """确为零参的旧jitter保留弃用警告。@return None。"""
    calls = []
    target = backoff.on_predicate(backoff.constant, interval=0, max_tries=2, jitter=lambda: 0, logger=None)(lambda: calls.append(1) or False)
    with pytest.warns(DeprecationWarning):
        assert target() is False
    assert len(calls) == 2
