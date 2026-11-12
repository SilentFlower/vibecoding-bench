"Public regression tests for PACKAGING-02-DEV; the complete business contract is in materials/PACKAGING-02-DEV-contract.md."
import unittest
from unittest.mock import patch
from packaging.markers import Marker,UndefinedEnvironmentName

def test_strict_partial_environment_rejects_missing_referenced_values():
    "Verify strict partial environment rejects missing referenced values."
    marker=Marker('python_version >= "3.8"')
    with patch('packaging.markers.default_environment',side_effect=AssertionError('不能访问宿主')):
        with unittest.TestCase().assertRaises(UndefinedEnvironmentName):marker.evaluate({'os_name':'posix'},strict=True)
        assert Marker('os_name == "posix"').evaluate({'os_name':'posix'},strict=True)

def test_context_defaults_dev_version_and_mapping_ownership():
    "Verify context defaults dev version and mapping ownership."
    environment={'python_full_version':'3.13.0+','os_name':'target'}
    assert Marker('python_full_version >= "3.13"').evaluate(environment,strict=True)
    assert environment=={'python_full_version':'3.13.0+','os_name':'target'}
    assert Marker('extra == ""').evaluate({},strict=True)
    assert Marker('"docs" in extras').evaluate({'extras':{'docs'}},context='lock_file',strict=True)
    with unittest.TestCase().assertRaises(UndefinedEnvironmentName):Marker('extra == ""').evaluate({},context='requirement',strict=True)

