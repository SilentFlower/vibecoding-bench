"Public regression tests for BOTTLE-O06-DEV; the complete business contract is in materials/BOTTLE-O06-DEV-contract.md."
import json
import bottle

def test_inventory_fields_and_order():
    "Verify inventory fields and order."
    app = bottle.Bottle()
    app.route('/first/<number:int>', method='POST', name='number', callback=lambda number: number)
    app.route('/second', callback=lambda: 'ok')
    rows = app.inspect_routes()
    assert [row['rule'] for row in rows] == ['/first/<number:int>', '/second']
    assert rows[0]['method'] == 'POST' and rows[0]['name'] == 'number' and rows[0]['filters'] == ['int']
    json.dumps(rows)

def test_no_config_or_callback_execution():
    "Verify no config or callback execution."
    app = bottle.Bottle()
    def endpoint():
        "Support the public regression through endpoint."
        raise AssertionError('not introspection')
    app.route('/secret', callback=endpoint, secret='never-export-value')
    assert 'never-export-value' not in json.dumps(app.inspect_routes())

def test_merged_owner_and_callable():
    "Verify merged owner and callable."
    class Endpoint:
        "Public regression fixture: Endpoint."
        def __call__(self):
            "Support the public regression through __call__."
            return 'ok'
    child, target = bottle.Bottle(), bottle.Bottle()
    child.route('/x', callback=Endpoint())
    target.merge(child)
    row = target.inspect_routes()[0]
    assert row['owner'] == 'external' and row['callback'] == 'Endpoint'
