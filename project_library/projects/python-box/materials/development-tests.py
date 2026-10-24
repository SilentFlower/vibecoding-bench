"""Public regressions: export sequences and Box values in frozen configuration to YAML without data loss."""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from box import Box, BoxError


def test_frozen_nested_list_roundtrip():
    """Export nested frozen sequences as ordinary YAML data. @return None."""
    source = {'services': [{'name': 'api', 'ports': [80, 443]}, {'name': 'worker', 'ports': []}]}
    config = Box(source, frozen_box=True)
    assert Box.from_yaml(config.to_yaml()).to_dict() == source


def test_nested_sequence_file_roundtrip_and_unicode():
    """Preserve nested sequences and Unicode text in actual file output. @return None."""
    source = {'routes': [[{'city': '杭州'}], [], [None, False, 0]]}
    config = Box(source, frozen_box=True)
    with TemporaryDirectory() as root:
        filename = Path(root) / 'settings.yml'
        config.to_yaml(filename=filename)
        assert Box.from_yaml(filename=filename).to_dict() == source


def test_serialization_does_not_unfreeze_source():
    """Keep root and nested mutations forbidden after a successful export. @return None."""
    config = Box({'items': [{'value': 3}]}, frozen_box=True)
    config.to_yaml()
    with pytest.raises(BoxError):
        config['new'] = 1
    with pytest.raises(BoxError):
        config['items'][0]['value'] = 4


def test_ordinary_yaml_remains_compatible():
    """Preserve YAML and JSON behavior for ordinary configuration. @return None."""
    source = {'settings': {'enabled': True}, 'names': ['a', 'b']}
    config = Box(source)
    assert Box.from_yaml(config.to_yaml()).to_dict() == source
    assert Box.from_json(config.to_json()).to_dict() == source
