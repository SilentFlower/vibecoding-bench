"""管理界面通过真实不可变快照读取handler而不执行业务对象。"""
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    """创建独立真实logger，避免触碰全局sink。@return Logger。"""
    logger.remove();result=deepcopy(logger);result.remove();return result

def test_ids_levels_types_and_detached_immutable_snapshot():
    """两种sink按id排序，返回项不能修改核心配置。@return None。"""
    import io
    log=clean();a=log.add(io.StringIO(),level='WARNING');b=log.add(lambda message:None,level='DEBUG',format=lambda record:'{message}')
    snapshot=log.handler_snapshot()
    assert isinstance(snapshot,tuple) and [item['id'] for item in snapshot]==[a,b]
    assert [item['level'] for item in snapshot]==[30,10]
    assert [item['sink_type'] for item in snapshot]==['StreamSink','CallableSink']
    assert [item['formatter'] for item in snapshot]==['static','callable']
    with pytest.raises(TypeError):snapshot[0]['level']=0
    log.remove(a);assert len(snapshot)==2 and len(log.handler_snapshot())==1
    log.remove()

def test_snapshot_does_not_call_sink_filter_or_formatter():
    """配置读取不触发业务write/filter/format或可变对象repr。@return None。"""
    calls=[];log=clean()
    def sink(message):calls.append('sink')
    def filter_(record):calls.append('filter');return True
    def formatter(record):calls.append('formatter');return '{message}'
    log.add(sink,filter=filter_,format=formatter)
    row=log.handler_snapshot()[0]
    assert row['filter']=='callable' and not row['enqueue'] and not calls
    log.remove()

def test_concurrent_add_remove_and_reads_are_consistent():
    """并发替换配置只看到完整映射，每个快照内部id唯一有序。@return None。"""
    from concurrent.futures import ThreadPoolExecutor
    log=clean()
    def mutate(index):
        identifier=log.add(lambda message:None);snapshot=log.handler_snapshot();log.remove(identifier)
        ids=[row['id'] for row in snapshot];assert ids==sorted(set(ids))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(mutate,range(20)))
    assert log.handler_snapshot()==()
