"Public regression tests for PACKAGING-01-DEV; the complete business contract is in materials/PACKAGING-01-DEV-contract.md."
import pickle
import unittest
from dataclasses import FrozenInstanceError
from packaging.display import DisplayVersion
from packaging.version import Version

def test_raw_spelling_comparison_hash_and_normalized_text():
    "Verify raw spelling comparison hash and normalized text."
    value=DisplayVersion(' v2026.01.01+ABC ')
    assert value.raw_version==' v2026.01.01+ABC ' and value.display==value.raw_version
    assert str(value)=='2026.1.1+abc' and value==Version('2026.1.1+abc')
    assert hash(value)==hash(Version('2026.1.1+abc')) and value<Version('2027')
    assert len({value,Version('2026.1.1+abc')})==1

def test_derived_version_pickle_and_readonly_policy():
    "Verify derived version pickle and readonly policy."
    value=DisplayVersion.from_version(Version.from_parts(release=(2,0)))
    assert value.raw_version is None and value.display=='2.0'
    restored=pickle.loads(pickle.dumps(DisplayVersion('02.00')))
    assert restored.raw_version=='02.00' and restored==value
    with unittest.TestCase().assertRaises(FrozenInstanceError):restored.raw_version='changed'

