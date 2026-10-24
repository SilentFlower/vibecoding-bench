"""抽象PathLike字段需要明确文本策略及读入目标。"""
from dataclasses import dataclass
from os import PathLike
from pathlib import Path, PurePosixPath
import pytest
from cattrs.preconf.json import make_converter

def test_abstract_path_json_roundtrip():
    """字段真实注解为PathLike[str]时可JSON往返。@return None。"""
    from cattrs.strategies.pathlike import configure_pathlike
    @dataclass
    class Record:
        """文件索引。"""
        location: PathLike[str]
    converter = configure_pathlike(make_converter(), factory=PurePosixPath)
    result = converter.loads(converter.dumps(Record(PurePosixPath('/virtual/x'))), Record)
    assert result.location == PurePosixPath('/virtual/x')

def test_custom_fspath_and_bytes_rejected():
    """自定义fspath可用，bytes不可隐式解码。@return None。"""
    from cattrs.strategies.pathlike import configure_pathlike
    converter = configure_pathlike(make_converter())
    class Custom:
        """文本路径实现。"""
        def __fspath__(self):
            """返回文本。@return str。"""
            return '/virtual/custom'
    assert converter.unstructure(Custom(), unstructure_as=PathLike[str]) == '/virtual/custom'
    with pytest.raises(TypeError): converter.structure(b'/bytes', PathLike[str])

def test_bad_factory_and_concrete_path():
    """工厂错误明确，具体Path已有能力保留。@return None。"""
    from cattrs.strategies.pathlike import configure_pathlike
    converter = configure_pathlike(make_converter(), factory=lambda value: value)
    with pytest.raises(TypeError): converter.structure('/virtual/x', PathLike[str])
    assert make_converter().unstructure(Path('/virtual/x')) == '/virtual/x'
