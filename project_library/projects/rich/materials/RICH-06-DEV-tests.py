"""单个Text的排版不会被无内容的分隔符模板覆盖。"""
import io
from rich.console import Console
from rich.text import Text


def render(text,**kwargs):
    """通过真实Console流水线收集文本。@param text 富文本。@param kwargs print参数。@return 输出。"""
    stream=io.StringIO();Console(file=stream,width=20,force_terminal=False,color_system=None).print(text,**kwargs)
    return stream.getvalue()


def test_single_text_self_justify_and_explicit_override():
    """内置center等价显式center，显式left仍优先。@return None。"""
    own=Text('hi',justify='center')
    assert render(own)==render(Text('hi'),justify='center')
    assert render(own,justify='left')==render(Text('hi'),justify='left')
    assert own.justify=='center'


def test_overflow_no_wrap_end_and_plain_string_compatibility():
    """不修改输入排版，end属于本轮print而非源对象。@return None。"""
    own=Text('a'*30,overflow='ellipsis',no_wrap=True,end='source')
    output=render(own,end='')
    assert len(output)<=20 and output.endswith('…')
    assert own.end=='source' and own.overflow=='ellipsis' and own.no_wrap
    assert render('plain')=='plain\n'

