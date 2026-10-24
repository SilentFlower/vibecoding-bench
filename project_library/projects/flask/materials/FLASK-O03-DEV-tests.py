"""工厂阶段聚合配置约束，只报告字段位置和约束不泄漏值。"""
from flask import Flask
import json

def test_required_types_enum_ranges_and_nested_errors_aggregate():
    """多个真实配置错误一次报告，并区分bool与int。@return None。"""
    app=Flask(__name__);app.config.update(LIMIT=True,MODE='invalid-secret',STORE={'PORT':70000},TOKEN=None)
    rules={'LIMIT':{'type':int,'minimum':1,'maximum':100},'MODE':{'choices':['safe']},'MISSING':{'required':True},'STORE':{'properties':{'PORT':{'type':int,'maximum':65535}}},'TOKEN':{'nullable':False}}
    rows=app.config.validate(rules)
    assert {(tuple(row['path']),row['code']) for row in rows}=={(('LIMIT',),'type'),(('MODE',),'choices'),(('MISSING',),'required'),(('STORE','PORT'),'maximum'),(('TOKEN',),'null')}
    assert 'invalid-secret' not in json.dumps(rows) and app.config['LIMIT'] is True

def test_valid_values_missing_optional_nullable_and_explicit_bool():
    """合法值不转换，缺省可选与明确nullable各自有效。@return None。"""
    app=Flask(__name__);app.config.update(LIMIT=20,MODE='safe',TOKEN=None,FLAG=True)
    assert app.config.validate({'LIMIT':{'type':int,'minimum':1,'maximum':100},'MODE':{'choices':['safe']},'TOKEN':{'nullable':True},'ABSENT':{'type':str},'FLAG':{'type':bool}})==[]
    assert type(app.config['LIMIT']) is int

def test_literal_dotted_keys_nested_missing_and_nonobject_are_distinct():
    """点号键按原字典键，嵌套用properties明确表示，类型错误不写配置。@return None。"""
    app=Flask(__name__);app.config.update({'LITERAL.KEY':'ok','STORE':{},'NOT_OBJECT':3})
    rows=app.config.validate({'LITERAL.KEY':{'type':str},'STORE':{'properties':{'VALUE':{'required':True}}},'NOT_OBJECT':{'properties':{'VALUE':{'required':True}}}})
    assert rows==[{'path':['STORE','VALUE'],'code':'required'},{'path':['NOT_OBJECT'],'code':'object'}]
