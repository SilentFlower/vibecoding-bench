"""流dump接受实际PathLike协议，目标流所有权仍在调用方。"""
from jinja2 import Environment
from pathlib import Path
from io import StringIO,BytesIO
import pytest

def test_pathlike_utf8_bytes_and_buffer_mode(tmp_path):
    """Path和字符串产生相同UTF8字节，开启缓冲也完整。@return None。"""
    template=Environment().from_string('你好,{{name}}!')
    path=tmp_path/'one';template.stream(name='世界').dump(path)
    other=tmp_path/'two';stream=template.stream(name='世界');stream.enable_buffering(2);stream.dump(str(other))
    assert path.read_bytes()==other.read_bytes()=='你好,世界!'.encode()

def test_custom_path_protocol_and_invalid_fspath(tmp_path):
    """调用标准协议而非str猜路径，错误返回类型拒绝。@return None。"""
    class Target:
        """有明确路径协议的业务目标。"""
        def __fspath__(self):return str(tmp_path/'custom')
    Environment().from_string('value').stream().dump(Target())
    assert (tmp_path/'custom').read_text()=='value'
    class Bad:
        """故意返回非法路径值。"""
        def __fspath__(self):return 123
    with pytest.raises(TypeError):Environment().from_string('x').stream().dump(Bad())

def test_caller_stream_not_closed_and_encoding_failure(tmp_path):
    """文本/二进制流归调用方，自开文件出错也关闭。@return None。"""
    template=Environment().from_string('中文')
    text=StringIO();template.stream().dump(text);assert text.getvalue()=='中文' and not text.closed
    binary=BytesIO();template.stream().dump(binary,encoding='utf8');assert binary.getvalue()=='中文'.encode() and not binary.closed
    with pytest.raises(UnicodeEncodeError):template.stream().dump(tmp_path/'bad',encoding='ascii')
