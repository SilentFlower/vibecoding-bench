"Public regression tests for BF-REUSE-DEV; the complete business contract is in materials/BF-REUSE-DEV-contract.md."
import asyncio
import logging
import pytest
import backoff


def test_reuse_exception_decorator(caplog):
    "Verify reuse exception decorator."
    calls = []
    decorate = backoff.on_exception(backoff.constant, ValueError, max_tries=1,
        logger='development.reuse', on_giveup=calls.append)
    def fail():
        "Support the public regression through fail."
        raise ValueError('target')
    with caplog.at_level(logging.ERROR, logger='development.reuse'):
        for _ in range(3):
            caplog.clear()
            with pytest.raises(ValueError):
                decorate(fail)()
            assert len(caplog.records) == 1
    assert len(calls) == 3


def test_reuse_predicate_and_generator_handlers(caplog):
    "Verify reuse predicate and generator handlers."
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
    "Verify reuse mixed sync async."
    decorate = backoff.on_predicate(backoff.constant, max_tries=1, logger='development.mixed')
    async def target():
        "Support the public regression through target."
        return False
    with caplog.at_level(logging.ERROR, logger='development.mixed'):
        decorate(lambda: False)()
        caplog.clear()
        assert asyncio.run(decorate(target)()) is False
        assert len(caplog.records) == 1
