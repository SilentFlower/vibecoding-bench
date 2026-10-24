"""局部静默策略在真实记录路径生效，不改变全局模块activation。"""
from copy import deepcopy
from loguru import logger
import asyncio
import pytest

def clean():
    """创建独立logger及真实输出列表。@return logger/messages。"""
    logger.remove();log=deepcopy(logger);log.remove();out=[];log.add(out.append,format='{level}:{message}');return log,out

def test_threshold_nested_and_exception_restore_actual_output():
    """阈值包含边界，嵌套只收紧，异常后完整恢复。@return None。"""
    log,out=clean()
    with log.silence('INFO'):
        log.info('hidden');log.warning('visible')
        with log.silence('ERROR'):log.warning('also hidden');log.critical('critical')
    with pytest.raises(ValueError):
        with log.silence(50):raise ValueError('body')
    log.info('restored');assert ''.join(out)=='WARNING:visible\nCRITICAL:critical\nINFO:restored\n';log.remove()

def test_async_siblings_and_new_threads_keep_contextvar_boundaries():
    """兄弟协程/新线程不被另一个上下文静默；子协程继承当前上下文。@return None。"""
    import threading
    log,out=clean()
    async def run():
        entered=asyncio.Event();release=asyncio.Event()
        async def muted():
            with log.silence('INFO'):
                entered.set();await release.wait();log.info('muted')
                await asyncio.create_task(child())
        async def child():log.info('inherited')
        async def sibling():await entered.wait();log.info('sibling');release.set()
        await asyncio.gather(muted(),sibling())
    asyncio.run(run())
    with log.silence('INFO'):
        thread=threading.Thread(target=lambda:log.info('thread'));thread.start();thread.join()
    assert ''.join(out)=='INFO:sibling\nINFO:thread\n';log.remove()

def test_module_match_logger_core_isolation_and_invalid_config():
    """模块点边界与logger核心隔离，参数错误在进入前拒绝。@return None。"""
    log,out=clean();other,other_out=clean()
    with log.silence('INFO',module=__name__):log.info('hidden');other.info('other')
    with log.silence('INFO',module='not-this-module'):log.info('visible')
    assert ''.join(out)=='INFO:visible\n' and ''.join(other_out)=='INFO:other\n'
    with pytest.raises(ValueError):
        with log.silence(True):pass
    with pytest.raises(TypeError):
        with log.silence(module=42):pass
    log.remove();other.remove()
