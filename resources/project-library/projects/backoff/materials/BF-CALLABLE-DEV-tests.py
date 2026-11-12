"Public regression tests for BF-CALLABLE-DEV; the complete business contract is in materials/BF-CALLABLE-DEV-contract.md."
from functools import partial
import logging
import pytest
import backoff


def test_partial_preserves_error(caplog):
    "Verify partial preserves error."
    error = ValueError('target')
    def fail(secret):
        "Support the public regression through fail."
        raise error
    target = backoff.on_exception(backoff.constant, ValueError, max_tries=1)(partial(fail, 'hidden-token'))
    with caplog.at_level(logging.ERROR, logger='backoff'):
        with pytest.raises(ValueError) as result:
            target()
    assert result.value is error
    assert 'fail' in caplog.text and 'hidden-token' not in caplog.text


def test_callable_instance(caplog):
    "Verify callable instance."
    class Endpoint:
        "Public regression fixture: Endpoint."
        def __call__(self):
            "Support the public regression through __call__."
            return 0
    with caplog.at_level(logging.ERROR, logger='backoff'):
        assert backoff.on_predicate(backoff.constant, max_tries=1)(Endpoint())() == 0
    assert 'Endpoint' in caplog.text


def test_logger_none_unchanged():
    "Verify logger none unchanged."
    assert backoff.on_predicate(backoff.constant, max_tries=1, logger=None)(partial(lambda x: x, 8))() == 8
