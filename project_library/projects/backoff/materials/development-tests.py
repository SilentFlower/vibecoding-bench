"""Public regressions: apply the same finite-wait exhaustion and give-up policy to synchronous and asynchronous retries."""
import asyncio
from unittest.mock import patch

import backoff
import pytest


def test_sync_exhaustion_respects_false():
    """Preserve explicitly requested None returns on exhaustion and invoke the callback once. @return None."""
    calls, given = [], []
    @backoff.on_exception(backoff.constant, ValueError, interval=[], jitter=None,
        logger=None, raise_on_giveup=False, on_giveup=given.append)
    def send():
        """Simulate a failed send. @return Does not return."""
        calls.append(1)
        raise ValueError('not sent')
    assert send() is None
    assert len(calls) == len(given) == 1
    assert isinstance(given[0]['exception'], ValueError)


def test_async_exhaustion_respects_false():
    """Apply the same exhaustion policy asynchronously and await the give-up callback. @return None."""
    calls, given = [], []
    async def record(details):
        """Save actual asynchronous callback details. @param details Callback details. @return None."""
        given.append(details)
    @backoff.on_exception(backoff.constant, OSError, interval=[0], jitter=None,
        logger=None, raise_on_giveup=False, on_giveup=record)
    async def send():
        """Simulate a failed asynchronous send. @return Does not return."""
        calls.append(1)
        raise OSError('offline')
    assert asyncio.run(send()) is None
    assert len(calls) == 2 and len(given) == 1 and given[0]['tries'] == 2


def test_raise_true_preserves_original_exception():
    """Preserve the same exception object under default and explicit re-raise policies. @return None."""
    failure = LookupError('same instance')
    @backoff.on_exception(backoff.constant, LookupError, interval=[], logger=None)
    def send():
        """Raise the fixed exception. @return Does not return."""
        raise failure
    with pytest.raises(LookupError) as caught:
        send()
    assert caught.value is failure


def test_success_and_predicate_controls():
    """Preserve business results on ordinary success and predicate exhaustion. @return None."""
    success = backoff.on_exception(backoff.constant, ValueError, interval=[], logger=None)(lambda: 19)
    predicate = backoff.on_predicate(backoff.constant, interval=[], logger=None)(lambda: 0)
    assert success() == 19 and predicate() == 0
