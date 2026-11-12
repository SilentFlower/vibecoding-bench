"Public regression tests for FLASK-O01-DEV; the complete business contract is in materials/FLASK-O01-DEV-contract.md."
from flask import Flask,Blueprint
from flask.cli import cli
import json

def test_json_manifest_actual_methods_defaults_blueprint_and_unicode():
    "Verify json manifest actual methods defaults blueprint and unicode."
    app=Flask(__name__,static_folder=None);blueprint=Blueprint('shop',__name__)
    blueprint.add_url_rule('/商品/<int:item>',endpoint='detail',view_func=lambda item:str(item),defaults={'mode':'正常'})
    app.register_blueprint(blueprint,url_prefix='/v1')
    result=app.test_cli_runner().invoke(cli,args=['routes','--format','json']);assert result.exit_code==0
    document=json.loads(result.output);assert document['schema']==1
    row=document['routes'][0];assert row['endpoint']=='shop.detail' and row['rule']=='/v1/商品/<int:item>'
    assert row['methods']==['GET','HEAD','OPTIONS'] and row['defaults']=={'mode':'正常'} and row['automatic_options']
    assert 'Endpoint' in app.test_cli_runner().invoke(cli,args=['routes']).output

def test_filters_empty_apps_and_multiple_rules_have_valid_one_document():
    "Verify filters empty apps and multiple rules have valid one document."
    app=Flask(__name__,static_folder=None)
    assert json.loads(app.test_cli_runner().invoke(cli,args=['routes','--format','json']).output)['routes']==[]
    app.add_url_rule('/a','shop.item',lambda:'a');app.add_url_rule('/b','shop.item',app.view_functions['shop.item']);app.add_url_rule('/c','other.item',lambda:'c')
    result=app.test_cli_runner().invoke(cli,args=['routes','--format','json','--blueprint','shop','--endpoint','shop.item'])
    rows=json.loads(result.output)['routes'];assert [row['rule'] for row in rows]==['/a','/b']

def test_opaque_defaults_no_repr_and_invalid_format_are_explicit():
    "Verify opaque defaults no repr and invalid format are explicit."
    class Opaque:
        "Public regression fixture: Opaque."
        def __repr__(self):raise AssertionError('repr must not run')
    app=Flask(__name__,static_folder=None);app.add_url_rule('/x','x',lambda **kwargs:'ok',defaults={'opaque':Opaque()})
    row=json.loads(app.test_cli_runner().invoke(cli,args=['routes','--format','json']).output)['routes'][0]
    assert row['defaults']=={'opaque':{'$type':'Opaque'}}
    assert app.test_cli_runner().invoke(cli,args=['routes','--format','guess']).exit_code!=0
