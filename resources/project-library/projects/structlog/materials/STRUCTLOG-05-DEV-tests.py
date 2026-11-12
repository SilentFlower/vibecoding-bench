"Public regression tests for STRUCTLOG-05-DEV; the complete business contract is in materials/STRUCTLOG-05-DEV-contract.md."
from structlog.testing import CapturingLogger,CapturingLoggerFactory

def test_oldest_or_newest_retention_total_and_dropped():
    "Verify oldest or newest retention total and dropped."
    for policy,expected in (('drop_oldest',[2,3]),('reject_new',[0,1])):
        logger=CapturingLogger(2,overflow=policy)
        for index in range(4):logger.info(index)
        assert [call.args[0] for call in logger.calls]==expected
        assert logger.total==4 and logger.dropped==2 and isinstance(logger.calls,list)
    logger=CapturingLogger()
    for index in range(4):logger.info(index)
    assert len(logger.calls)==4 and logger.dropped==0

def test_zero_capacity_factory_reuse_and_snapshot_independence():
    "Verify zero capacity factory reuse and snapshot independence."
    factory=CapturingLoggerFactory(1);logger=factory();assert factory('name') is logger
    logger.info('first',key='old');snapshot=logger.snapshot();logger.info('second',key='new')
    assert snapshot[0].args==('first',) and snapshot[0].kwargs=={'key':'old'}
    snapshot[0].kwargs['key']='changed';assert logger.calls[0].kwargs=={'key':'new'}
    logger=CapturingLogger(0);logger.error('ignored')
    assert logger.calls==[] and logger.total==1 and logger.dropped==1

