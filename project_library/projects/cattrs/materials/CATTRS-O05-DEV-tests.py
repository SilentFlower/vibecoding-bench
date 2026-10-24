"Public regression tests for CATTRS-O05-DEV; the complete business contract is in materials/CATTRS-O05-DEV-contract.md."
from dataclasses import dataclass
from os import PathLike
from pathlib import Path, PurePosixPath
import pytest
from cattrs.preconf.json import make_converter

def test_abstract_path_json_roundtrip():
    "Verify abstract path json roundtrip."
    from cattrs.strategies.pathlike import configure_pathlike
    @dataclass
    class Record:
        "Public regression fixture: Record."
        location: PathLike[str]
    converter = configure_pathlike(make_converter(), factory=PurePosixPath)
    result = converter.loads(converter.dumps(Record(PurePosixPath('/virtual/x'))), Record)
    assert result.location == PurePosixPath('/virtual/x')

def test_custom_fspath_and_bytes_rejected():
    "Verify custom fspath and bytes rejected."
    from cattrs.strategies.pathlike import configure_pathlike
    converter = configure_pathlike(make_converter())
    class Custom:
        "Public regression fixture: Custom."
        def __fspath__(self):
            "Support the public regression through __fspath__."
            return '/virtual/custom'
    assert converter.unstructure(Custom(), unstructure_as=PathLike[str]) == '/virtual/custom'
    with pytest.raises(TypeError): converter.structure(b'/bytes', PathLike[str])

def test_bad_factory_and_concrete_path():
    "Verify bad factory and concrete path."
    from cattrs.strategies.pathlike import configure_pathlike
    converter = configure_pathlike(make_converter(), factory=lambda value: value)
    with pytest.raises(TypeError): converter.structure('/virtual/x', PathLike[str])
    assert make_converter().unstructure(Path('/virtual/x')) == '/virtual/x'
