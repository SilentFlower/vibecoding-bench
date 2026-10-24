"""条件必需字段在缺失时也必须检查。"""
from cerberus import Validator

def test_missing_condition_true_and_false():
    """kind决定缺失value是否必需，不反转dependencies。@return None。"""
    validator = Validator({'kind': {}, 'value': {'required_if': {'field': 'kind', 'equals': 'choice'}}})
    assert not validator.validate({'kind': 'choice'})
    assert validator.validate({'kind': 'free'})
    assert validator.validate({'kind': 'choice', 'value': 0})

def test_defaults_and_update():
    """默认值先归一化，update模式保持原必需政策。@return None。"""
    schema = {'kind': {'default': 'choice'}, 'value': {'required_if': {'field': 'kind', 'equals': 'choice'}}}
    assert not Validator(schema).validate({})
    assert Validator(schema).validate({}, update=True)
    schema['value']['default'] = 7
    assert Validator(schema).validate({})

def test_root_false_and_nullable():
    """False条件和根字段引用不被误作缺失。@return None。"""
    validator = Validator({'enabled': {}, 'child': {'type': 'dict', 'schema': {'value': {'nullable': True, 'required_if': {'field': '^enabled', 'equals': False}}}}})
    assert not validator.validate({'enabled': False, 'child': {}})
    assert validator.validate({'enabled': False, 'child': {'value': None}})
