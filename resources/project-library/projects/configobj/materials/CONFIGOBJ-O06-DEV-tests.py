"Public regression tests for CONFIGOBJ-O06-DEV; the complete business contract is in materials/CONFIGOBJ-O06-DEV-contract.md."
from configobj import ConfigObj
from configobj.validate import Validator
import pytest

def test_success_converts_types_replaces_old_and_rebinds(tmp_path):
    "Verify success converts types replaces old and rebinds."
    path=tmp_path/'settings.ini';path.write_text('x=1\n[child]\ny=2\n')
    cfg=ConfigObj(str(path),configspec=['x=integer','[child]','y=integer']);identity=id(cfg)
    assert cfg.validate(Validator()) is True
    path.write_text('# next\nx=3\n[child]\ny=4\n')
    report=cfg.validated_reload(Validator())
    assert report['valid'] and id(cfg)==identity and cfg['x']==3 and cfg['child']['y']==4
    assert cfg['child'].parent is cfg and cfg['child'].main is cfg and cfg.initial_comment==['# next']

def test_validation_failure_keeps_old_values_comments_and_spec(tmp_path):
    "Verify validation failure keeps old values comments and spec."
    path=tmp_path/'settings.ini';path.write_text('# old\nx=1\n')
    cfg=ConfigObj(str(path),configspec=['x=integer']);cfg.validate(Validator());spec=cfg.configspec
    path.write_text('x=bad\n')
    assert cfg.validated_reload(Validator())['valid'] is False
    assert cfg['x']==1 and cfg.initial_comment==['# old'] and cfg.configspec is spec

def test_missing_and_parse_failure_leave_old_tree(tmp_path):
    "Verify missing and parse failure leave old tree."
    path=tmp_path/'settings.ini';path.write_text('x=1\n')
    cfg=ConfigObj(str(path),configspec=['x=integer']);cfg.validate(Validator())
    path.unlink()
    with pytest.raises(OSError):cfg.validated_reload(Validator())
    assert cfg['x']==1 and not path.exists()
    path.write_text('invalid line\n')
    with pytest.raises(SyntaxError):cfg.validated_reload(Validator())
    assert cfg['x']==1
