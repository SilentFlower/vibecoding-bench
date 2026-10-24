"""模板引擎扩展名不能污染父类或其他实例。"""
import bottle
from pathlib import Path

def test_engine_local_search(tmp_path):
    """每个适配器优先匹配自己的扩展名。@param tmp_path 临时目录。@return None。"""
    for extension in ('tpl', 'mako', 'jinja2', 'tmpl'):
        (tmp_path / ('view.' + extension)).write_text(extension)
    assert bottle.MakoTemplate.search('view', [str(tmp_path)]).endswith('.mako')
    assert bottle.Jinja2Template.search('view', [str(tmp_path)]).endswith('.jinja2')
    assert bottle.CheetahTemplate.search('view', [str(tmp_path)]).endswith('.tmpl')
    assert bottle.BaseTemplate.search('view', [str(tmp_path)]).endswith('.tpl')

def test_instance_extension_isolation(tmp_path):
    """实例追加扩展仅对该实例生效且真实渲染。@param tmp_path 临时目录。@return None。"""
    (tmp_path / 'view.business').write_text('Hello {{value}}')
    before = list(bottle.SimpleTemplate.extensions)
    instance = bottle.SimpleTemplate(name=Path('view'), lookup=tmp_path, extensions=['business'])
    assert instance.render(value='x') == 'Hello x'
    assert list(bottle.SimpleTemplate.extensions) == before

def test_default_fallback_and_invalid(tmp_path):
    """已有tpl后备保持，坏扩展明确拒绝。@param tmp_path 临时目录。@return None。"""
    import pytest
    (tmp_path / 'legacy.tpl').write_text('legacy')
    assert bottle.MakoTemplate.search('legacy', [str(tmp_path)]).endswith('.tpl')
    with pytest.raises(ValueError): bottle.SimpleTemplate(source='x', extensions=['../bad'])
