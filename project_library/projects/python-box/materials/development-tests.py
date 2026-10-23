"""公开回归：冻结配置内的序列和Box可以无损导出YAML。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from box import Box, BoxError


def test_frozen_nested_list_roundtrip():
    """嵌套冻结序列必须导出普通YAML数据。@return None。"""
    source = {'services': [{'name': 'api', 'ports': [80, 443]}, {'name': 'worker', 'ports': []}]}
    config = Box(source, frozen_box=True)
    assert Box.from_yaml(config.to_yaml()).to_dict() == source


def test_nested_sequence_file_roundtrip_and_unicode():
    """真实文件输出保留多层序列与中文。@return None。"""
    source = {'routes': [[{'city': '杭州'}], [], [None, False, 0]]}
    config = Box(source, frozen_box=True)
    with TemporaryDirectory() as root:
        filename = Path(root) / 'settings.yml'
        config.to_yaml(filename=filename)
        assert Box.from_yaml(filename=filename).to_dict() == source


def test_serialization_does_not_unfreeze_source():
    """导出成功后源配置仍拒绝根和嵌套修改。@return None。"""
    config = Box({'items': [{'value': 3}]}, frozen_box=True)
    config.to_yaml()
    with pytest.raises(BoxError):
        config['new'] = 1
    with pytest.raises(BoxError):
        config['items'][0]['value'] = 4


def test_ordinary_yaml_remains_compatible():
    """普通配置的YAML和JSON行为保持。@return None。"""
    source = {'settings': {'enabled': True}, 'names': ['a', 'b']}
    config = Box(source)
    assert Box.from_yaml(config.to_yaml()).to_dict() == source
    assert Box.from_json(config.to_json()).to_dict() == source
