"""分发文件名从结构化数据构造，不扩大兼容tag集合。"""
import unittest
from packaging.tags import Tag
from packaging.version import Version
from packaging.utils import build_wheel_filename,build_sdist_filename,parse_wheel_filename,parse_sdist_filename,InvalidWheelFilename

def test_wheel_and_sdist_semantic_roundtrip_and_stable_tags():
    """名字转义、build、版本和压缩tag均可反向解析。@return None。"""
    tags={Tag('py3','none','any'),Tag('py2','none','any')}
    name=build_wheel_filename('My.Pkg','01.2',tags,(3,'abc'))
    assert name=='my_pkg-1.2-3abc-py2.py3-none-any.whl'
    assert parse_wheel_filename(name)==('my-pkg',Version('1.2'),(3,'abc'),tags)
    assert parse_sdist_filename(build_sdist_filename('My.Pkg','1.0+local'))==('my-pkg',Version('1.0+local'))

def test_nonrectangular_tags_and_invalid_build_are_rejected():
    """不能让两标签压缩后变成四个兼容组合。@return None。"""
    tags={Tag('py2','none','any'),Tag('py3','abi3','any')}
    with unittest.TestCase().assertRaises(InvalidWheelFilename):build_wheel_filename('pkg','1',tags)
    with unittest.TestCase().assertRaises(InvalidWheelFilename):build_wheel_filename('pkg','1',{Tag('py3','none','any')},(True,'x'))

