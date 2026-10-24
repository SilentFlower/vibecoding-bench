"""显式事务环境加载先完成真实解析及路径检查再发布配置。"""
from flask import Flask
from copy import deepcopy
import pytest

def test_parent_child_conflict_rolls_back_entire_batch_and_nested_aliases(monkeypatch):
    """不是只恢复顶层值，已有嵌套外部对象也不能被半修改。@return None。"""
    app=Flask(__name__);original={'KEEP':{'value':1}};app.config['TREE']=original;before=deepcopy(dict(app.config))
    monkeypatch.setenv('REVIEW_A','2');monkeypatch.setenv('REVIEW_TREE__KEEP__value','3');monkeypatch.setenv('REVIEW_Z','3');monkeypatch.setenv('REVIEW_Z__LEAF','4')
    with pytest.raises(ValueError,match='REVIEW_Z__LEAF'):app.config.from_prefixed_env('REVIEW',atomic=True)
    assert dict(app.config)==before and original=={'KEEP':{'value':1}}

def test_success_json_types_non_strict_string_and_empty_paths(monkeypatch):
    """合法布尔/数字/嵌套共同生效，宽松解析保留字符串，空路径拒绝。@return None。"""
    app=Flask(__name__);monkeypatch.setenv('REVIEW_ENABLED','true');monkeypatch.setenv('REVIEW_STORE__PORT','8080');monkeypatch.setenv('REVIEW_TEXT','plain')
    assert app.config.from_prefixed_env('REVIEW',atomic=True) and app.config['ENABLED'] is True and app.config['STORE']['PORT']==8080 and app.config['TEXT']=='plain'
    monkeypatch.setenv('REVIEW_BAD____LEAF','1');before=deepcopy(dict(app.config))
    with pytest.raises(ValueError):app.config.from_prefixed_env('REVIEW',atomic=True)
    assert dict(app.config)==before

def test_strict_parse_and_programming_failures_preserve_old_state_legacy_default(monkeypatch):
    """严格解析及自定义加载器编程异常均回滚，默认旧宽松行为保持。@return None。"""
    app=Flask(__name__);monkeypatch.setenv('REVIEW_A','1');monkeypatch.setenv('REVIEW_Z','not-json');before=deepcopy(dict(app.config))
    with pytest.raises(ValueError,match='REVIEW_Z'):app.config.from_prefixed_env('REVIEW',atomic=True,strict=True)
    assert dict(app.config)==before
    def broken(value):raise RuntimeError('programming failure')
    with pytest.raises(RuntimeError):app.config.from_prefixed_env('REVIEW',atomic=True,loads=broken)
    assert dict(app.config)==before
    app.config.from_prefixed_env('REVIEW');assert app.config['A']==1 and app.config['Z']=='not-json'
