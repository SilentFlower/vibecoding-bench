"Public regression tests for ICECREAM-O05-DEV; the complete business contract is in materials/ICECREAM-O05-DEV-contract.md."
import logging,inspect
from pathlib import Path

def test_real_logrecord_source_and_passthrough():
    "Verify real logrecord source and passthrough."
    from icecream.logging_adapter import LoggingDebugger
    records=[]
    class Handler(logging.Handler):
        "Public regression fixture: Handler."
        def emit(self,record):records.append(record)
    logger=logging.Logger('test',logging.DEBUG);logger.addHandler(Handler());debug=LoggingDebugger(logger,prefix='test|')
    value=object();line=inspect.currentframe().f_lineno+1
    assert debug(value) is value
    assert records[0].lineno==line and records[0].funcName=='test_real_logrecord_source_and_passthrough' and Path(records[0].pathname)==Path(__file__)
    assert records[0].getMessage().startswith('test|')

def test_level_disabled_skips_all_formatting_and_same_values():
    "Verify level disabled skips all formatting and same values."
    from icecream.logging_adapter import LoggingDebugger
    class Bad:
        "Public regression fixture: Bad."
        def __repr__(self):raise AssertionError('repr')
    def badprefix():raise AssertionError('prefix')
    debug=LoggingDebugger(logging.Logger('quiet',logging.ERROR),prefix=badprefix)
    value=Bad();assert debug(value) is value and debug(1,2)==(1,2) and debug() is None

def test_debugger_disabled_and_handler_failure_propagates():
    "Verify debugger disabled and handler failure propagates."
    from icecream.logging_adapter import LoggingDebugger
    import pytest
    class Broken(logging.Handler):
        "Public regression fixture: Broken."
        def emit(self,record):raise OSError('handler')
    logger=logging.Logger('broken',logging.DEBUG);logger.addHandler(Broken());debug=LoggingDebugger(logger)
    debug.disable();assert debug(9)==9;debug.enable()
    with pytest.raises(OSError):debug(9)
