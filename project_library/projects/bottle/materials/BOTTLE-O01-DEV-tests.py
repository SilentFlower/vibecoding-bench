"""真实PathLike应作为路径，流所有权保持。"""
import io
from pathlib import Path
import bottle

def test_upload_path_and_stream(tmp_path):
    """路径和目录上传实际保存，外部流不关闭。@param tmp_path 临时目录。@return None。"""
    upload = bottle.FileUpload(io.BytesIO(b'hello'), 'file', 'name.txt')
    upload.save(tmp_path / 'target.txt')
    assert (tmp_path / 'target.txt').read_bytes() == b'hello'
    output = io.BytesIO()
    upload.save(output)
    assert output.getvalue() == b'hello' and not output.closed

def test_template_pathlike_lookup(tmp_path):
    """模板名和单目录PathLike真实渲染。@param tmp_path 临时目录。@return None。"""
    (tmp_path / 'view.tpl').write_text('Hello {{name}}', encoding='utf-8')
    template = bottle.SimpleTemplate(name=Path('view'), lookup=tmp_path)
    assert template.render(name='world') == 'Hello world'

def test_custom_fspath_and_invalid(tmp_path):
    """遵守__fspath__协议，不用str伪造路径。@param tmp_path 临时目录。@return None。"""
    import pytest
    class Location:
        """自定义真实路径。"""
        def __fspath__(self):
            """返回本次目标。@return 字符串路径。"""
            return str(tmp_path / 'custom.txt')
    bottle.FileUpload(io.BytesIO(b'x'), 'file', 'x').save(Location())
    assert (tmp_path / 'custom.txt').read_bytes() == b'x'
    class Invalid:
        """错误路径协议。"""
        def __fspath__(self):
            """故意返回非法类型。@return int。"""
            return 7
    with pytest.raises(TypeError): bottle.FileUpload(io.BytesIO(b'x'), 'file', 'x').save(Invalid())
