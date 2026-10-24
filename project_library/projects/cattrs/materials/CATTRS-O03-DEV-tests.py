"""base64策略应双向且严格，不影响其他预配置实例。"""
from dataclasses import dataclass
import pytest
from cattrs.preconf.json import make_converter

def test_standard_and_nested_roundtrip():
    """嵌套bytes真实JSON往返。@return None。"""
    from cattrs.strategies.base64 import configure_base64
    @dataclass
    class Packet:
        """二进制载荷。"""
        payload: bytes
    converter = configure_base64(make_converter())
    assert converter.unstructure(b'hello') == 'aGVsbG8='
    assert converter.loads(converter.dumps(Packet(b'\x00\xff')), Packet) == Packet(b'\x00\xff')

def test_invalid_padding_and_characters():
    """坏padding、非ASCII和非法字符拒绝。@return None。"""
    from cattrs.strategies.base64 import configure_base64
    converter = configure_base64(make_converter())
    for value in ['aGVsbG8', '!!!!', '中文']:
        with pytest.raises(ValueError): converter.structure(value, bytes)
    assert converter.structure('', bytes) == b''

def test_urlsafe_and_default_isolation():
    """显式URL字母表和未配置实例默认可区分。@return None。"""
    from cattrs.strategies.base64 import configure_base64
    converter = configure_base64(make_converter(), urlsafe=True)
    assert converter.unstructure(b'\xfb\xff') == '-_8='
    assert converter.structure('-_8=', bytes) == b'\xfb\xff'
    assert make_converter().unstructure(b'hello') != 'aGVsbG8='
