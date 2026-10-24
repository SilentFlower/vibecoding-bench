"Public regression tests for FLASK-O02-DEV; the complete business contract is in materials/FLASK-O02-DEV-contract.md."
from flask import Flask
from functools import wraps

def test_duplicate_method_missing_view_and_signature_are_reported():
    "Verify duplicate method missing view and signature are reported."
    app=Flask(__name__,static_folder=None);calls=[]
    app.add_url_rule('/same','first',lambda:'one');app.add_url_rule('/same','second',lambda:'two')
    app.add_url_rule('/orphan','orphan');app.add_url_rule('/item/<int:item_id>','bad',lambda:'no argument')
    before=list(app.url_map.iter_rules());diagnostics=app.validate_routes()
    assert any(row['code']=='overlap' and row['methods']==['GET'] for row in diagnostics)
    assert any(row['code']=='missing_view' and row['endpoint']=='orphan' for row in diagnostics)
    assert any(row['code']=='view_signature' and row['endpoint']=='bad' for row in diagnostics)
    assert list(app.url_map.iter_rules())==before and not calls

def test_valid_kwargs_defaults_wrapped_methods_and_build_only_are_not_false_errors():
    "Verify valid kwargs defaults wrapped methods and build only are not false errors."
    from flask.views import MethodView
    app=Flask(__name__,static_folder=None)
    def original(item=1):return str(item)
    @wraps(original)
    def wrapped(*args,**kwargs):return original(*args,**kwargs)
    app.add_url_rule('/a/<int:item>','a',wrapped);app.add_url_rule('/b/<int:item>','b',lambda **kwargs:'ok')
    app.add_url_rule('/build/<x>','build',build_only=True)
    class View(MethodView):
        "Public regression fixture: View."
        def get(self,item):return str(item)
    app.add_url_rule('/c/<item>',view_func=View.as_view('c'))
    assert app.validate_routes()==[]

def test_nonidentical_patterns_and_value_preprocessors_are_not_speculatively_rejected():
    "Verify nonidentical patterns and value preprocessors are not speculatively rejected."
    app=Flask(__name__,static_folder=None)
    app.add_url_rule('/<int:value>','int',lambda value:'int');app.add_url_rule('/<string:value>','text',lambda value:'text')
    app.add_url_rule('/injected/<item>','injected',lambda:'ok')
    @app.url_value_preprocessor
    def consume(endpoint,values):
        if values:values.pop('item',None)
    assert app.validate_routes()==[]
