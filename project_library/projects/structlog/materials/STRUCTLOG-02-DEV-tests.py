"""递归模式解码数据值但不改键或共享输入。"""
import unittest
from structlog.processors import UnicodeDecoder

def test_recursive_builtin_containers_preserve_type_keys_and_input():
    """Unicode值真实转换，tuple/list区分且原树保持。@return None。"""
    nested={'name':'中文'.encode(),'items':[b'a',(b'b',)]};source={b'key':nested,'opaque':object()}
    result=UnicodeDecoder(recursive=True)(None,'info',source)
    assert result[b'key']=={'name':'中文','items':['a',('b',)]}
    assert source[b'key'] is nested and isinstance(nested['name'],bytes)
    assert result['opaque'] is source['opaque'] and type(result[b'key']['items'][1]) is tuple

def test_errors_cycle_shared_dag_depth_and_default_shallow():
    """共享子树不是循环，默认仍只解码顶层。@return None。"""
    child=[b'x'];source={'a':child,'b':child}
    assert UnicodeDecoder(recursive=True)(None,'info',source)=={'a':['x'],'b':['x']}
    cycle=[];cycle.append(cycle)
    with unittest.TestCase().assertRaisesRegex(ValueError,'循环'):UnicodeDecoder(recursive=True)(None,'info',{'x':cycle})
    with unittest.TestCase().assertRaises(ValueError):UnicodeDecoder(recursive=True,max_depth=0)(None,'info',{'x':[]})
    with unittest.TestCase().assertRaises(UnicodeDecodeError):UnicodeDecoder(errors='strict',recursive=True)(None,'info',{'x':[b'\xff']})
    values={'x':[b'a'],'y':b'b'};assert UnicodeDecoder()(None,'info',values) is values and values=={'x':[b'a'],'y':'b'}

