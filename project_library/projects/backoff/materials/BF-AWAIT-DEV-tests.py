"Public regression tests for BF-AWAIT-DEV; the complete business contract is in materials/BF-AWAIT-DEV-contract.md."
import asyncio
import backoff


def test_async_callable_giveup():
    "Verify async callable giveup."
    class Giveup:
        "Public regression fixture: Giveup."
        async def __call__(self, error):
            "Support the public regression through __call__."
            await asyncio.sleep(0)
            return False
    calls = []
    @backoff.on_exception(backoff.constant, ValueError, interval=0, jitter=None, max_tries=2, giveup=Giveup(), logger=None)
    async def target():
        "Support the public regression through target."
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('retry')
        return 7
    assert asyncio.run(target()) == 7
    assert len(calls) == 2


def test_wrapped_awaitable_handler():
    "Verify wrapped awaitable handler."
    seen = []
    async def record(details):
        "Support the public regression through record."
        await asyncio.sleep(0)
        seen.append(details['tries'])
    @backoff.on_predicate(backoff.constant, logger=None, on_success=lambda details: record(details))
    async def target():
        "Support the public regression through target."
        return 3
    assert asyncio.run(target()) == 3
    assert seen == [1]


def test_sync_handler_remains_supported():
    "Verify sync handler remains supported."
    seen = []
    @backoff.on_predicate(backoff.constant, logger=None, on_success=seen.append)
    async def target():
        "Support the public regression through target."
        return 2
    assert asyncio.run(target()) == 2
    assert len(seen) == 1
