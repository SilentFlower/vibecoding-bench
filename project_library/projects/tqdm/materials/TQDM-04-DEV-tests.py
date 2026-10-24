"""异步as_completed可接纳标准库支持的无长度任务生成器。"""
import asyncio
from tqdm.asyncio import tqdm_asyncio


def test_task_generator_consumed_once_and_all_results_match():
    """任务只生产一次，未知总量不强行len。@return None。"""
    async def run():
        """本地任务，无网络。@return 完成值。"""
        produced=[]
        async def work(value):await asyncio.sleep(0);return value
        def tasks():
            """按需产生真实asyncio Task。@return 迭代器。"""
            for value in range(4):produced.append(value);yield asyncio.create_task(work(value))
        result=[await future for future in tqdm_asyncio.as_completed(tasks(),disable=True)]
        assert produced==list(range(4)) and sorted(result)==list(range(4))
    asyncio.run(run())


def test_empty_explicit_total_and_exception_propagation():
    """空源、显式total和任务异常沿标准库语义。@return None。"""
    async def run():
        """异步边界矩阵。@return None。"""
        assert [await future for future in tqdm_asyncio.as_completed((item for item in []),disable=True)]==[]
        async def work():return 7
        assert [await future for future in tqdm_asyncio.as_completed((asyncio.create_task(work()) for _ in range(1)),total=1,disable=True)]==[7]
        async def broken():raise ValueError('task failure')
        try:
            for future in tqdm_asyncio.as_completed((asyncio.create_task(broken()) for _ in range(1)),disable=True):await future
        except ValueError:pass
        else:raise AssertionError('任务异常被吞')
    asyncio.run(run())

