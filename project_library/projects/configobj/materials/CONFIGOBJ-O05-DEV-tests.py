"""固定验证报告不被失败字典真值误导，也不输出秘密值。"""
import json
from configobj import ConfigObj
from configobj.validate import Validator

def test_valid_report_and_default_paths_no_mutation():
    """真实转换和默认路径可以预览，原配置不变。@return None。"""
    cfg=ConfigObj(['port=42'],configspec=['port=integer','name=string(default=demo)'])
    report=cfg.validate_report(Validator())
    assert report['valid'] is True and report['issues']==[] and report['applied'] is False
    assert report['changed_paths']==[['name'],['port']] and report['defaulted_paths']==[['name']]
    assert cfg['port']=='42' and 'name' not in cfg

def test_nested_failures_safe_and_json_serializable():
    """完整节路径和错误类别保留，消息不带原值。@return None。"""
    cfg=ConfigObj(['[server]','port=secret-value'],configspec=['[server]','port=integer','host=string'])
    report=cfg.validate_report(Validator())
    assert report['valid'] is False and len(report['issues'])==2
    assert ['server','port'] in [row['path'] for row in report['issues']]
    assert 'secret-value' not in json.dumps(report) and 'integer' not in json.dumps(report)

def test_explicit_apply_preserves_old_validate_api():
    """只有显式apply执行原生类型转换。@return None。"""
    cfg=ConfigObj(['x=2'],configspec=['x=integer'])
    assert cfg.validate_report(Validator(),apply=True)['applied'] is True and cfg['x']==2
    assert cfg.validate(Validator()) is True
