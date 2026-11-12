"Public regression tests for TQDM-03-DEV; the complete business contract is in materials/TQDM-03-DEV-contract.md."
import io
import array
import unittest
from tqdm.utils import CallbackIOWrapper


def test_binary_memoryview_and_short_write_return_value():
    "Verify binary memoryview and short write return value."
    values=[];stream=io.BytesIO();wrapped=CallbackIOWrapper(values.append,stream,method='write')
    view=memoryview(array.array('I',[1,2,3]));result=wrapped.write(view)
    assert result==view.nbytes and values==[view.nbytes] and len(stream.getvalue())==view.nbytes
    class Short:
        "Public regression fixture: Short."
        def write(self,data):
            "Support the public regression through write."
            return 2
    values=[];assert CallbackIOWrapper(values.append,Short(),method='write').write(b'abcdef')==2
    assert values==[2]


def test_text_none_zero_and_write_error_do_not_overcount():
    "Verify text none zero and write error do not overcount."
    values=[];stream=io.StringIO();assert CallbackIOWrapper(values.append,stream,method='write').write('中文')==2 and values==[2]
    class Custom:
        "Public regression fixture: Custom."
        def __init__(self,value):self.value=value
        def write(self,data):
            "Support the public regression through write."
            if isinstance(self.value,Exception):raise self.value
            return self.value
    values=[];assert CallbackIOWrapper(values.append,Custom(None),method='write').write(b'abc') is None and values==[3]
    values=[];assert CallbackIOWrapper(values.append,Custom(0),method='write').write(b'abc')==0 and values==[0]
    values=[]
    with unittest.TestCase().assertRaises(OSError):CallbackIOWrapper(values.append,Custom(OSError('failed')),method='write').write(b'abc')
    assert values==[]

