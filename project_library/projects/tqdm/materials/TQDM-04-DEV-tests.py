"Public regression tests for TQDM-04-DEV; the complete business contract is in materials/TQDM-04-DEV-contract.md."
import asyncio
from tqdm.asyncio import tqdm_asyncio


def test_task_generator_consumed_once_and_all_results_match():
    "Verify task generator consumed once and all results match."
    async def run():
        "Support the public regression through run."
        produced=[]
        async def work(value):await asyncio.sleep(0);return value
        def tasks():
            "Support the public regression through tasks."
            for value in range(4):produced.append(value);yield asyncio.create_task(work(value))
        result=[await future for future in tqdm_asyncio.as_completed(tasks(),disable=True)]
        assert produced==list(range(4)) and sorted(result)==list(range(4))
    asyncio.run(run())


def test_empty_explicit_total_and_exception_propagation():
    "Verify empty explicit total and exception propagation."
    async def run():
        "Support the public regression through run."
        assert [await future for future in tqdm_asyncio.as_completed((item for item in []),disable=True)]==[]
        async def work():return 7
        assert [await future for future in tqdm_asyncio.as_completed((asyncio.create_task(work()) for _ in range(1)),total=1,disable=True)]==[7]
        async def broken():raise ValueError('task failure')
        try:
            for future in tqdm_asyncio.as_completed((asyncio.create_task(broken()) for _ in range(1)),disable=True):await future
        except ValueError:pass
        else:raise AssertionError('任务异常被吞')
    asyncio.run(run())

