"Public regression tests for LOGURU-O01-DEV; the complete business contract is in materials/LOGURU-O01-DEV-contract.md."
from copy import deepcopy
from loguru import logger
import pytest

def clean():
    "Support the public regression through clean."
    logger.remove();result=deepcopy(logger);result.remove();return result

def test_ids_levels_types_and_detached_immutable_snapshot():
    "Verify ids levels types and detached immutable snapshot."
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
    "Verify snapshot does not call sink filter or formatter."
    calls=[];log=clean()
    def sink(message):calls.append('sink')
    def filter_(record):calls.append('filter');return True
    def formatter(record):calls.append('formatter');return '{message}'
    log.add(sink,filter=filter_,format=formatter)
    row=log.handler_snapshot()[0]
    assert row['filter']=='callable' and not row['enqueue'] and not calls
    log.remove()

def test_concurrent_add_remove_and_reads_are_consistent():
    "Verify concurrent add remove and reads are consistent."
    from concurrent.futures import ThreadPoolExecutor
    log=clean()
    def mutate(index):
        identifier=log.add(lambda message:None);snapshot=log.handler_snapshot();log.remove(identifier)
        ids=[row['id'] for row in snapshot];assert ids==sorted(set(ids))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(mutate,range(20)))
    assert log.handler_snapshot()==()
