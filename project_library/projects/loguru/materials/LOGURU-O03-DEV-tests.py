"Public regression tests for LOGURU-O03-DEV; the complete business contract is in materials/LOGURU-O03-DEV-contract.md."
from copy import deepcopy
from loguru import logger
import asyncio
import pytest

def clean():
    "Support the public regression through clean."
    logger.remove();log=deepcopy(logger);log.remove();out=[];log.add(out.append,format='{level}:{message}');return log,out

def test_threshold_nested_and_exception_restore_actual_output():
    "Verify threshold nested and exception restore actual output."
    log,out=clean()
    with log.silence('INFO'):
        log.info('hidden');log.warning('visible')
        with log.silence('ERROR'):log.warning('also hidden');log.critical('critical')
    with pytest.raises(ValueError):
        with log.silence(50):raise ValueError('body')
    log.info('restored');assert ''.join(out)=='WARNING:visible\nCRITICAL:critical\nINFO:restored\n';log.remove()

def test_async_siblings_and_new_threads_keep_contextvar_boundaries():
    "Verify async siblings and new threads keep contextvar boundaries."
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
    "Verify module match logger core isolation and invalid config."
    log,out=clean();other,other_out=clean()
    with log.silence('INFO',module=__name__):log.info('hidden');other.info('other')
    with log.silence('INFO',module='not-this-module'):log.info('visible')
    assert ''.join(out)=='INFO:visible\n' and ''.join(other_out)=='INFO:other\n'
    with pytest.raises(ValueError):
        with log.silence(True):pass
    with pytest.raises(TypeError):
        with log.silence(module=42):pass
    log.remove();other.remove()
