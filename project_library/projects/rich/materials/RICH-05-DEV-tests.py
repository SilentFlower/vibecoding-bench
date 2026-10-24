"Public regression tests for RICH-05-DEV; the complete business contract is in materials/RICH-05-DEV-contract.md."
import io
from rich.console import Console
from rich.traceback import Traceback


def test_non_string_syntax_message_renders_the_original_problem():
    "Verify non string syntax message renders the original problem."
    error=SyntaxError();error.msg=123;error.filename='example.py';error.text='bad source';error.lineno=1;error.offset=1
    trace=Traceback.extract(type(error),error,None)
    assert trace.stacks[0].syntax_error.msg=='123'
    output=io.StringIO();Console(file=output,force_terminal=False,width=80).print(Traceback(trace))
    assert '123' in output.getvalue() and 'SyntaxError' in output.getvalue()


def test_message_str_failure_has_stable_fallback_without_mutation():
    "Verify message str failure has stable fallback without mutation."
    class Broken:
        "Public regression fixture: Broken."
        def __str__(self):
            "Support the public regression through __str__."
            raise RuntimeError('broken str')
    original=Broken();error=SyntaxError();error.msg=original;error.text='x';error.offset=1
    trace=Traceback.extract(type(error),error,None)
    assert trace.stacks[0].syntax_error.msg=='<exception str() failed>' and error.msg is original
    output=io.StringIO();Console(file=output,force_terminal=False).print(Traceback(trace))
    assert 'exception str() failed' in output.getvalue()

