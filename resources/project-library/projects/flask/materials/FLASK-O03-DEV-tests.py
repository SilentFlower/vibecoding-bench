"Public regression tests for FLASK-O03-DEV; the complete business contract is in materials/FLASK-O03-DEV-contract.md."
from flask import Flask
import json

def test_required_types_enum_ranges_and_nested_errors_aggregate():
    "Verify required types enum ranges and nested errors aggregate."
    app=Flask(__name__);app.config.update(LIMIT=True,MODE='invalid-secret',STORE={'PORT':70000},TOKEN=None)
    rules={'LIMIT':{'type':int,'minimum':1,'maximum':100},'MODE':{'choices':['safe']},'MISSING':{'required':True},'STORE':{'properties':{'PORT':{'type':int,'maximum':65535}}},'TOKEN':{'nullable':False}}
    rows=app.config.validate(rules)
    assert {(tuple(row['path']),row['code']) for row in rows}=={(('LIMIT',),'type'),(('MODE',),'choices'),(('MISSING',),'required'),(('STORE','PORT'),'maximum'),(('TOKEN',),'null')}
    assert 'invalid-secret' not in json.dumps(rows) and app.config['LIMIT'] is True

def test_valid_values_missing_optional_nullable_and_explicit_bool():
    "Verify valid values missing optional nullable and explicit bool."
    app=Flask(__name__);app.config.update(LIMIT=20,MODE='safe',TOKEN=None,FLAG=True)
    assert app.config.validate({'LIMIT':{'type':int,'minimum':1,'maximum':100},'MODE':{'choices':['safe']},'TOKEN':{'nullable':True},'ABSENT':{'type':str},'FLAG':{'type':bool}})==[]
    assert type(app.config['LIMIT']) is int

def test_literal_dotted_keys_nested_missing_and_nonobject_are_distinct():
    "Verify literal dotted keys nested missing and nonobject are distinct."
    app=Flask(__name__);app.config.update({'LITERAL.KEY':'ok','STORE':{},'NOT_OBJECT':3})
    rows=app.config.validate({'LITERAL.KEY':{'type':str},'STORE':{'properties':{'VALUE':{'required':True}}},'NOT_OBJECT':{'properties':{'VALUE':{'required':True}}}})
    assert rows==[{'path':['STORE','VALUE'],'code':'required'},{'path':['NOT_OBJECT'],'code':'object'}]
