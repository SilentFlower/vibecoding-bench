"Public regression tests for BOTTLE-O02-DEV; the complete business contract is in materials/BOTTLE-O02-DEV-contract.md."
import bottle
from pathlib import Path

def test_engine_local_search(tmp_path):
    "Verify engine local search."
    for extension in ('tpl', 'mako', 'jinja2', 'tmpl'):
        (tmp_path / ('view.' + extension)).write_text(extension)
    assert bottle.MakoTemplate.search('view', [str(tmp_path)]).endswith('.mako')
    assert bottle.Jinja2Template.search('view', [str(tmp_path)]).endswith('.jinja2')
    assert bottle.CheetahTemplate.search('view', [str(tmp_path)]).endswith('.tmpl')
    assert bottle.BaseTemplate.search('view', [str(tmp_path)]).endswith('.tpl')

def test_instance_extension_isolation(tmp_path):
    "Verify instance extension isolation."
    (tmp_path / 'view.business').write_text('Hello {{value}}')
    before = list(bottle.SimpleTemplate.extensions)
    instance = bottle.SimpleTemplate(name=Path('view'), lookup=tmp_path, extensions=['business'])
    assert instance.render(value='x') == 'Hello x'
    assert list(bottle.SimpleTemplate.extensions) == before

def test_default_fallback_and_invalid(tmp_path):
    "Verify default fallback and invalid."
    import pytest
    (tmp_path / 'legacy.tpl').write_text('legacy')
    assert bottle.MakoTemplate.search('legacy', [str(tmp_path)]).endswith('.tpl')
    with pytest.raises(ValueError): bottle.SimpleTemplate(source='x', extensions=['../bad'])
