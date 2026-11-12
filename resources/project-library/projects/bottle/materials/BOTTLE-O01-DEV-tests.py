"Public regression tests for BOTTLE-O01-DEV; the complete business contract is in materials/BOTTLE-O01-DEV-contract.md."
import io
from pathlib import Path
import bottle

def test_upload_path_and_stream(tmp_path):
    "Verify upload path and stream."
    upload = bottle.FileUpload(io.BytesIO(b'hello'), 'file', 'name.txt')
    upload.save(tmp_path / 'target.txt')
    assert (tmp_path / 'target.txt').read_bytes() == b'hello'
    output = io.BytesIO()
    upload.save(output)
    assert output.getvalue() == b'hello' and not output.closed

def test_template_pathlike_lookup(tmp_path):
    "Verify template pathlike lookup."
    (tmp_path / 'view.tpl').write_text('Hello {{name}}', encoding='utf-8')
    template = bottle.SimpleTemplate(name=Path('view'), lookup=tmp_path)
    assert template.render(name='world') == 'Hello world'

def test_custom_fspath_and_invalid(tmp_path):
    "Verify custom fspath and invalid."
    import pytest
    class Location:
        "Public regression fixture: Location."
        def __fspath__(self):
            "Support the public regression through __fspath__."
            return str(tmp_path / 'custom.txt')
    bottle.FileUpload(io.BytesIO(b'x'), 'file', 'x').save(Location())
    assert (tmp_path / 'custom.txt').read_bytes() == b'x'
    class Invalid:
        "Public regression fixture: Invalid."
        def __fspath__(self):
            "Support the public regression through __fspath__."
            return 7
    with pytest.raises(TypeError): bottle.FileUpload(io.BytesIO(b'x'), 'file', 'x').save(Invalid())
