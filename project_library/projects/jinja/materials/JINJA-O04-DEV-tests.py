"Public regression tests for JINJA-O04-DEV; the complete business contract is in materials/JINJA-O04-DEV-contract.md."
from jinja2 import Environment
from pathlib import Path
from io import StringIO,BytesIO
import pytest

def test_pathlike_utf8_bytes_and_buffer_mode(tmp_path):
    "Verify pathlike utf8 bytes and buffer mode."
    template=Environment().from_string('你好,{{name}}!')
    path=tmp_path/'one';template.stream(name='世界').dump(path)
    other=tmp_path/'two';stream=template.stream(name='世界');stream.enable_buffering(2);stream.dump(str(other))
    assert path.read_bytes()==other.read_bytes()=='你好,世界!'.encode()

def test_custom_path_protocol_and_invalid_fspath(tmp_path):
    "Verify custom path protocol and invalid fspath."
    class Target:
        "Public regression fixture: Target."
        def __fspath__(self):return str(tmp_path/'custom')
    Environment().from_string('value').stream().dump(Target())
    assert (tmp_path/'custom').read_text()=='value'
    class Bad:
        "Public regression fixture: Bad."
        def __fspath__(self):return 123
    with pytest.raises(TypeError):Environment().from_string('x').stream().dump(Bad())

def test_caller_stream_not_closed_and_encoding_failure(tmp_path):
    "Verify caller stream not closed and encoding failure."
    template=Environment().from_string('中文')
    text=StringIO();template.stream().dump(text);assert text.getvalue()=='中文' and not text.closed
    binary=BytesIO();template.stream().dump(binary,encoding='utf8');assert binary.getvalue()=='中文'.encode() and not binary.closed
    with pytest.raises(UnicodeEncodeError):template.stream().dump(tmp_path/'bad',encoding='ascii')
