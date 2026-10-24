"""旧sdist歧义是显式审查，不更改现代解析默认值。"""
import unittest
from packaging.utils import parse_legacy_sdist_filename,parse_sdist_filename,InvalidSdistFilename
from packaging.version import Version

def test_legacy_post_version_expected_name_or_all_candidates():
    """cffi旧post写法需已知名称才能选定。@return None。"""
    assert parse_legacy_sdist_filename('cffi-1.0.2-2.tar.gz','cffi')==('cffi',Version('1.0.2.post2'))
    candidates=parse_legacy_sdist_filename('cffi-1.0.2-2.tar.gz')
    assert ('cffi',Version('1.0.2.post2')) in candidates and ('cffi-1-0-2',Version('2')) in candidates
    assert parse_sdist_filename('cffi-1.0.2-2.tar.gz')==('cffi-1-0-2',Version('2'))

def test_normal_names_expected_mismatch_and_invalid_archives():
    """现代名称仍可列候选，期望不匹配须拒绝。@return None。"""
    assert parse_legacy_sdist_filename('my-pkg-1.2.zip','My_Pkg')==('my-pkg',Version('1.2'))
    for filename,expected in (('pkg-1.zip','other'),('pkg-bad.tar.gz',None),('pkg-1.whl',None)):
        with unittest.TestCase().assertRaises(InvalidSdistFilename):parse_legacy_sdist_filename(filename,expected)

