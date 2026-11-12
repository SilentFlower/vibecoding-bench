"Public regression tests for PACKAGING-05-DEV; the complete business contract is in materials/PACKAGING-05-DEV-contract.md."
import unittest
from packaging.tags import Tag
from packaging.version import Version
from packaging.utils import build_wheel_filename,build_sdist_filename,parse_wheel_filename,parse_sdist_filename,InvalidWheelFilename

def test_wheel_and_sdist_semantic_roundtrip_and_stable_tags():
    "Verify wheel and sdist semantic roundtrip and stable tags."
    tags={Tag('py3','none','any'),Tag('py2','none','any')}
    name=build_wheel_filename('My.Pkg','01.2',tags,(3,'abc'))
    assert name=='my_pkg-1.2-3abc-py2.py3-none-any.whl'
    assert parse_wheel_filename(name)==('my-pkg',Version('1.2'),(3,'abc'),tags)
    assert parse_sdist_filename(build_sdist_filename('My.Pkg','1.0+local'))==('my-pkg',Version('1.0+local'))

def test_nonrectangular_tags_and_invalid_build_are_rejected():
    "Verify nonrectangular tags and invalid build are rejected."
    tags={Tag('py2','none','any'),Tag('py3','abi3','any')}
    with unittest.TestCase().assertRaises(InvalidWheelFilename):build_wheel_filename('pkg','1',tags)
    with unittest.TestCase().assertRaises(InvalidWheelFilename):build_wheel_filename('pkg','1',{Tag('py3','none','any')},(True,'x'))

