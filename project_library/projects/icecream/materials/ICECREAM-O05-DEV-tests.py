"""真实LogRecord保留用户来源，禁用级别不调用repr或格式器。"""
import logging,inspect
from pathlib import Path

def test_real_logrecord_source_and_passthrough():
    """文件、行号、函数名属于用户调用。@return None。"""
    from icecream.logging_adapter import LoggingDebugger
    records=[]
    class Handler(logging.Handler):
        """捕获实际标准日志记录。"""
        def emit(self,record):records.append(record)
    logger=logging.Logger('test',logging.DEBUG);logger.addHandler(Handler());debug=LoggingDebugger(logger,prefix='test|')
    value=object();line=inspect.currentframe().f_lineno+1
    assert debug(value) is value
    assert records[0].lineno==line and records[0].funcName=='test_real_logrecord_source_and_passthrough' and Path(records[0].pathname)==Path(__file__)
    assert records[0].getMessage().startswith('test|')

def test_level_disabled_skips_all_formatting_and_same_values():
    """被过滤日志不执行昂贵repr或prefix回调。@return None。"""
    from icecream.logging_adapter import LoggingDebugger
    class Bad:
        """禁用日志不能触碰repr。"""
        def __repr__(self):raise AssertionError('repr')
    def badprefix():raise AssertionError('prefix')
    debug=LoggingDebugger(logging.Logger('quiet',logging.ERROR),prefix=badprefix)
    value=Bad();assert debug(value) is value and debug(1,2)==(1,2) and debug() is None

def test_debugger_disabled_and_handler_failure_propagates():
    """调试器独立关闭，handler错误沿原logging策略传播。@return None。"""
    from icecream.logging_adapter import LoggingDebugger
    import pytest
    class Broken(logging.Handler):
        """合成故障handler。"""
        def emit(self,record):raise OSError('handler')
    logger=logging.Logger('broken',logging.DEBUG);logger.addHandler(Broken());debug=LoggingDebugger(logger)
    debug.disable();assert debug(9)==9;debug.enable()
    with pytest.raises(OSError):debug(9)
