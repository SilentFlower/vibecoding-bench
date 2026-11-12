"Public regression tests for RICH-06-DEV; the complete business contract is in materials/RICH-06-DEV-contract.md."
import io
from rich.console import Console
from rich.text import Text


def render(text,**kwargs):
    "Support the public regression through render."
    stream=io.StringIO();Console(file=stream,width=20,force_terminal=False,color_system=None).print(text,**kwargs)
    return stream.getvalue()


def test_single_text_self_justify_and_explicit_override():
    "Verify single text self justify and explicit override."
    own=Text('hi',justify='center')
    assert render(own)==render(Text('hi'),justify='center')
    assert render(own,justify='left')==render(Text('hi'),justify='left')
    assert own.justify=='center'


def test_overflow_no_wrap_end_and_plain_string_compatibility():
    "Verify overflow no wrap end and plain string compatibility."
    own=Text('a'*30,overflow='ellipsis',no_wrap=True,end='source')
    output=render(own,end='')
    assert len(output)<=20 and output.endswith('…')
    assert own.end=='source' and own.overflow=='ellipsis' and own.no_wrap
    assert render('plain')=='plain\n'

