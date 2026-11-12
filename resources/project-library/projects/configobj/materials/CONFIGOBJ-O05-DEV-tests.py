"Public regression tests for CONFIGOBJ-O05-DEV; the complete business contract is in materials/CONFIGOBJ-O05-DEV-contract.md."
import json
from configobj import ConfigObj
from configobj.validate import Validator

def test_valid_report_and_default_paths_no_mutation():
    "Verify valid report and default paths no mutation."
    cfg=ConfigObj(['port=42'],configspec=['port=integer','name=string(default=demo)'])
    report=cfg.validate_report(Validator())
    assert report['valid'] is True and report['issues']==[] and report['applied'] is False
    assert report['changed_paths']==[['name'],['port']] and report['defaulted_paths']==[['name']]
    assert cfg['port']=='42' and 'name' not in cfg

def test_nested_failures_safe_and_json_serializable():
    "Verify nested failures safe and json serializable."
    cfg=ConfigObj(['[server]','port=secret-value'],configspec=['[server]','port=integer','host=string'])
    report=cfg.validate_report(Validator())
    assert report['valid'] is False and len(report['issues'])==2
    assert ['server','port'] in [row['path'] for row in report['issues']]
    assert 'secret-value' not in json.dumps(report) and 'integer' not in json.dumps(report)

def test_explicit_apply_preserves_old_validate_api():
    "Verify explicit apply preserves old validate api."
    cfg=ConfigObj(['x=2'],configspec=['x=integer'])
    assert cfg.validate_report(Validator(),apply=True)['applied'] is True and cfg['x']==2
    assert cfg.validate(Validator()) is True
