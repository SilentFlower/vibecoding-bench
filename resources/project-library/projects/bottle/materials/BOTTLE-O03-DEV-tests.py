"Public regression tests for BOTTLE-O03-DEV; the complete business contract is in materials/BOTTLE-O03-DEV-contract.md."
import bottle

def test_prefixed_clone_and_reverse_url():
    "Verify prefixed clone and reverse url."
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/item/<name>', name='item', callback=lambda name: name)
    target.merge(child, prefix='/v1/')
    assert child.routes[0].rule == '/item/<name>'
    assert target.routes[0].rule == '/v1/item/<name>' and target.routes[0].app is target
    assert target.get_url('item', name='x') == '/v1/item/x'

def test_legacy_owner_and_plugins():
    "Verify legacy owner and plugins."
    child, legacy, target = bottle.Bottle(), bottle.Bottle(), bottle.Bottle()
    child.route('/x', callback=lambda: 'ok', apply=[lambda callback: callback])
    legacy.merge(child)
    target.merge(child, prefix='/api')
    assert legacy.routes[0] is child.routes[0]
    assert target.routes[0].plugins == child.routes[0].plugins
    assert target.routes[0].plugins is not child.routes[0].plugins

def test_invalid_and_conflicting_names():
    "Verify invalid and conflicting names."
    import pytest
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/x', name='same', callback=lambda: 'child')
    target.route('/y', name='same', callback=lambda: 'target')
    with pytest.raises(ValueError): target.merge(child, prefix='/api')
    with pytest.raises(ValueError): target.merge(child, prefix='relative')
    assert len(target.routes) == 1
