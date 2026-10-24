"""重复endpoint失败后真实路由表与分发行为完全保持。"""
from flask import Flask,Blueprint
import pytest

def test_failed_new_address_does_not_dispatch_old_view_or_enter_map():
    """原版抛异常后/new仍可命中旧视图，本目标真正移除该半注册副作用。@return None。"""
    app=Flask(__name__,static_folder=None);old=lambda:'old';new=lambda:'new';app.add_url_rule('/old','saved',old)
    before=list(app.url_map.iter_rules());views=dict(app.view_functions)
    with pytest.raises(AssertionError):app.add_url_rule('/new','saved',new)
    assert list(app.url_map.iter_rules())==before and app.view_functions==views
    client=app.test_client();assert client.get('/old').data==b'old' and client.get('/new').status_code==404

def test_same_view_multiple_rules_and_none_view_registration_remain_valid():
    """合法同视图别名与后绑定视图模式仍可注册。@return None。"""
    app=Flask(__name__,static_folder=None);view=lambda:'same';app.add_url_rule('/a','shared',view);app.add_url_rule('/b','shared',view)
    app.add_url_rule('/later','later');app.view_functions['later']=lambda:'bound'
    assert app.test_client().get('/a').data==app.test_client().get('/b').data==b'same'
    assert app.test_client().get('/later').data==b'bound'

def test_methods_defaults_and_blueprint_conflict_keep_exact_previous_state():
    """冲突带额外method/default也不能改变现有匹配器。@return None。"""
    app=Flask(__name__,static_folder=None);app.add_url_rule('/old','group.saved',lambda **kwargs:'old',methods=['GET'])
    before=[(rule.rule,rule.endpoint,rule.methods,rule.defaults) for rule in app.url_map.iter_rules()]
    with pytest.raises(AssertionError):app.add_url_rule('/failed','group.saved',lambda **kwargs:'new',methods=['POST'],defaults={'x':1})
    after=[(rule.rule,rule.endpoint,rule.methods,rule.defaults) for rule in app.url_map.iter_rules()]
    assert after==before and app.test_client().post('/failed').status_code==404
