"""路由清单是稳定可读元数据，不能泄漏秘密配置或执行回调。"""
import json
import bottle

def test_inventory_fields_and_order():
    """真实动态路由的方法、名字和过滤器可读。@return None。"""
    app = bottle.Bottle()
    app.route('/first/<number:int>', method='POST', name='number', callback=lambda number: number)
    app.route('/second', callback=lambda: 'ok')
    rows = app.inspect_routes()
    assert [row['rule'] for row in rows] == ['/first/<number:int>', '/second']
    assert rows[0]['method'] == 'POST' and rows[0]['name'] == 'number' and rows[0]['filters'] == ['int']
    json.dumps(rows)

def test_no_config_or_callback_execution():
    """闭包不执行，配置secret不进入清单。@return None。"""
    app = bottle.Bottle()
    def endpoint():
        """禁止执行。@return 不返回。"""
        raise AssertionError('not introspection')
    app.route('/secret', callback=endpoint, secret='never-export-value')
    assert 'never-export-value' not in json.dumps(app.inspect_routes())

def test_merged_owner_and_callable():
    """旧合并owner可解释，无函数名对象安全降级。@return None。"""
    class Endpoint:
        """业务目标对象。"""
        def __call__(self):
            """返回结果。@return 字符串。"""
            return 'ok'
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/x', callback=Endpoint())
    target.merge(child)
    row = target.inspect_routes()[0]
    assert row['owner'] == 'external' and row['callback'] == 'Endpoint'
