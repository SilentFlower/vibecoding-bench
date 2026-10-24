"""前缀合并克隆规则并明确目标应用插件归属。"""
import bottle

def test_prefixed_clone_and_reverse_url():
    """源规则不变，目标反向URL包含前缀。@return None。"""
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/item/<name>', name='item', callback=lambda name: name)
    target.merge(child, prefix='/v1/')
    assert child.routes[0].rule == '/item/<name>'
    assert target.routes[0].rule == '/v1/item/<name>' and target.routes[0].app is target
    assert target.get_url('item', name='x') == '/v1/item/x'

def test_legacy_owner_and_plugins():
    """旧merge保持owner，前缀副本保留路由专有插件列表。@return None。"""
    child, legacy, target = bottle.Bottle(), bottle.Bottle(), bottle.Bottle()
    child.route('/x', callback=lambda: 'ok', apply=[lambda callback: callback])
    legacy.merge(child)
    target.merge(child, prefix='/api')
    assert legacy.routes[0] is child.routes[0]
    assert target.routes[0].plugins == child.routes[0].plugins
    assert target.routes[0].plugins is not child.routes[0].plugins

def test_invalid_and_conflicting_names():
    """坏前缀和重名在添加前拒绝。@return None。"""
    import pytest
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/x', name='same', callback=lambda: 'child')
    target.route('/y', name='same', callback=lambda: 'target')
    with pytest.raises(ValueError): target.merge(child, prefix='/api')
    with pytest.raises(ValueError): target.merge(child, prefix='relative')
    assert len(target.routes) == 1
