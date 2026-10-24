"""IO进度报告真实成功量，不把memoryview元素数当字节数。"""
import io
import array
import unittest
from tqdm.utils import CallbackIOWrapper


def test_binary_memoryview_and_short_write_return_value():
    """真实BytesIO按12字节更新，短写只更新返回部分。@return None。"""
    values=[];stream=io.BytesIO();wrapped=CallbackIOWrapper(values.append,stream,method='write')
    view=memoryview(array.array('I',[1,2,3]));result=wrapped.write(view)
    assert result==view.nbytes and values==[view.nbytes] and len(stream.getvalue())==view.nbytes
    class Short:
        """合法短写流。"""
        def write(self,data):
            """只写前两字节。@param data 输入。@return 2。"""
            return 2
    values=[];assert CallbackIOWrapper(values.append,Short(),method='write').write(b'abcdef')==2
    assert values==[2]


def test_text_none_zero_and_write_error_do_not_overcount():
    """文本按字符，None兼容回退，错误不先更新。@return None。"""
    values=[];stream=io.StringIO();assert CallbackIOWrapper(values.append,stream,method='write').write('中文')==2 and values==[2]
    class Custom:
        """可控制返回和异常的流。"""
        def __init__(self,value):self.value=value
        def write(self,data):
            """真实调用后才计量。@param data 输入。@return 配置值。"""
            if isinstance(self.value,Exception):raise self.value
            return self.value
    values=[];assert CallbackIOWrapper(values.append,Custom(None),method='write').write(b'abc') is None and values==[3]
    values=[];assert CallbackIOWrapper(values.append,Custom(0),method='write').write(b'abc')==0 and values==[0]
    values=[]
    with unittest.TestCase().assertRaises(OSError):CallbackIOWrapper(values.append,Custom(OSError('failed')),method='write').write(b'abc')
    assert values==[]

