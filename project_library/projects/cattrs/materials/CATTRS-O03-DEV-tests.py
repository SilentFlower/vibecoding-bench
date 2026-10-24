"Public regression tests for CATTRS-O03-DEV; the complete business contract is in materials/CATTRS-O03-DEV-contract.md."
from dataclasses import dataclass
import pytest
from cattrs.preconf.json import make_converter

def test_standard_and_nested_roundtrip():
    "Verify standard and nested roundtrip."
    from cattrs.strategies.base64 import configure_base64
    @dataclass
    class Packet:
        "Public regression fixture: Packet."
        payload: bytes
    converter = configure_base64(make_converter())
    assert converter.unstructure(b'hello') == 'aGVsbG8='
    assert converter.loads(converter.dumps(Packet(b'\x00\xff')), Packet) == Packet(b'\x00\xff')

def test_invalid_padding_and_characters():
    "Verify invalid padding and characters."
    from cattrs.strategies.base64 import configure_base64
    converter = configure_base64(make_converter())
    for value in ['aGVsbG8', '!!!!', '中文']:
        with pytest.raises(ValueError): converter.structure(value, bytes)
    assert converter.structure('', bytes) == b''

def test_urlsafe_and_default_isolation():
    "Verify urlsafe and default isolation."
    from cattrs.strategies.base64 import configure_base64
    converter = configure_base64(make_converter(), urlsafe=True)
    assert converter.unstructure(b'\xfb\xff') == '-_8='
    assert converter.structure('-_8=', bytes) == b'\xfb\xff'
    assert make_converter().unstructure(b'hello') != 'aGVsbG8='
