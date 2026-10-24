"Public regression tests for PACKAGING-06-DEV; the complete business contract is in materials/PACKAGING-06-DEV-contract.md."
import unittest
from packaging.utils import parse_legacy_sdist_filename,parse_sdist_filename,InvalidSdistFilename
from packaging.version import Version

def test_legacy_post_version_expected_name_or_all_candidates():
    "Verify legacy post version expected name or all candidates."
    assert parse_legacy_sdist_filename('cffi-1.0.2-2.tar.gz','cffi')==('cffi',Version('1.0.2.post2'))
    candidates=parse_legacy_sdist_filename('cffi-1.0.2-2.tar.gz')
    assert ('cffi',Version('1.0.2.post2')) in candidates and ('cffi-1-0-2',Version('2')) in candidates
    assert parse_sdist_filename('cffi-1.0.2-2.tar.gz')==('cffi-1-0-2',Version('2'))

def test_normal_names_expected_mismatch_and_invalid_archives():
    "Verify normal names expected mismatch and invalid archives."
    assert parse_legacy_sdist_filename('my-pkg-1.2.zip','My_Pkg')==('my-pkg',Version('1.2'))
    for filename,expected in (('pkg-1.zip','other'),('pkg-bad.tar.gz',None),('pkg-1.whl',None)):
        with unittest.TestCase().assertRaises(InvalidSdistFilename):parse_legacy_sdist_filename(filename,expected)

