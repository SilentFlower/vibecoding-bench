"""失败原子保留，成功重接根与嵌套类型。"""
from configobj import ConfigObj
from configobj.validate import Validator
import pytest

def test_success_converts_types_replaces_old_and_rebinds(tmp_path):
    """新文件完成验证后整体接管，根身份保持。@return None。"""
    path=tmp_path/'settings.ini';path.write_text('x=1\n[child]\ny=2\n')
    cfg=ConfigObj(str(path),configspec=['x=integer','[child]','y=integer']);identity=id(cfg)
    assert cfg.validate(Validator()) is True
    path.write_text('# next\nx=3\n[child]\ny=4\n')
    report=cfg.validated_reload(Validator())
    assert report['valid'] and id(cfg)==identity and cfg['x']==3 and cfg['child']['y']==4
    assert cfg['child'].parent is cfg and cfg['child'].main is cfg and cfg.initial_comment==['# next']

def test_validation_failure_keeps_old_values_comments_and_spec(tmp_path):
    """非法新值不能部分污染已验证旧配置。@return None。"""
    path=tmp_path/'settings.ini';path.write_text('# old\nx=1\n')
    cfg=ConfigObj(str(path),configspec=['x=integer']);cfg.validate(Validator());spec=cfg.configspec
    path.write_text('x=bad\n')
    assert cfg.validated_reload(Validator())['valid'] is False
    assert cfg['x']==1 and cfg.initial_comment==['# old'] and cfg.configspec is spec

def test_missing_and_parse_failure_leave_old_tree(tmp_path):
    """丢失文件及语法错误均保留旧树。@return None。"""
    path=tmp_path/'settings.ini';path.write_text('x=1\n')
    cfg=ConfigObj(str(path),configspec=['x=integer']);cfg.validate(Validator())
    path.unlink()
    with pytest.raises(OSError):cfg.validated_reload(Validator())
    assert cfg['x']==1 and not path.exists()
    path.write_text('invalid line\n')
    with pytest.raises(SyntaxError):cfg.validated_reload(Validator())
    assert cfg['x']==1
