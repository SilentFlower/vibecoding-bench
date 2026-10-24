"""严格目标环境不从宿主补齐，默认覆盖模式仍保留。"""
import unittest
from unittest.mock import patch
from packaging.markers import Marker,UndefinedEnvironmentName

def test_strict_partial_environment_rejects_missing_referenced_values():
    """即使宿主提供值，严格求值仍明确缺失。@return None。"""
    marker=Marker('python_version >= "3.8"')
    with patch('packaging.markers.default_environment',side_effect=AssertionError('不能访问宿主')):
        with unittest.TestCase().assertRaises(UndefinedEnvironmentName):marker.evaluate({'os_name':'posix'},strict=True)
        assert Marker('os_name == "posix"').evaluate({'os_name':'posix'},strict=True)

def test_context_defaults_dev_version_and_mapping_ownership():
    """context既有默认与目标dev修正不修改来源映射。@return None。"""
    environment={'python_full_version':'3.13.0+','os_name':'target'}
    assert Marker('python_full_version >= "3.13"').evaluate(environment,strict=True)
    assert environment=={'python_full_version':'3.13.0+','os_name':'target'}
    assert Marker('extra == ""').evaluate({},strict=True)
    assert Marker('"docs" in extras').evaluate({'extras':{'docs'}},context='lock_file',strict=True)
    with unittest.TestCase().assertRaises(UndefinedEnvironmentName):Marker('extra == ""').evaluate({},context='requirement',strict=True)

