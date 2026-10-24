"""原异常的非字符串消息不能被二次渲染错误掩盖。"""
import io
from rich.console import Console
from rich.traceback import Traceback


def test_non_string_syntax_message_renders_the_original_problem():
    """实际提取并渲染，而非只检查数据类类型。@return None。"""
    error=SyntaxError();error.msg=123;error.filename='example.py';error.text='bad source';error.lineno=1;error.offset=1
    trace=Traceback.extract(type(error),error,None)
    assert trace.stacks[0].syntax_error.msg=='123'
    output=io.StringIO();Console(file=output,force_terminal=False,width=80).print(Traceback(trace))
    assert '123' in output.getvalue() and 'SyntaxError' in output.getvalue()


def test_message_str_failure_has_stable_fallback_without_mutation():
    """损坏的__str__安全回退，不改原异常对象。@return None。"""
    class Broken:
        """字符串转换自身失败的原消息。"""
        def __str__(self):
            """模拟第三方异常对象。@return 不返回。"""
            raise RuntimeError('broken str')
    original=Broken();error=SyntaxError();error.msg=original;error.text='x';error.offset=1
    trace=Traceback.extract(type(error),error,None)
    assert trace.stacks[0].syntax_error.msg=='<exception str() failed>' and error.msg is original
    output=io.StringIO();Console(file=output,force_terminal=False).print(Traceback(trace))
    assert 'exception str() failed' in output.getvalue()

