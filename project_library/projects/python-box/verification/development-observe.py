"""独立冻结YAML矩阵：真实解析、嵌套序列、内存隔离和冻结保护。"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import box
from box import Box, BoxError


def observations():
    """使用两个解析入口比较数据，不要求候选匹配任何文本格式。@return 业务事实。"""
    samples = [
        {'matrix': [[{'id': 17}, {'id': 19}], [], [None, False, 0, '雪']]},
        {'deep': {'members': [{'flags': {'ok': True}, 'tags': ['one', 'two']}]}, 'empty': []},
        {'x': [{'nested': [[{'value': 2.5}]]}]},
    ]
    roundtrip, unchanged, frozen, files = True, True, True, True
    for source in samples:
        config = Box(source, frozen_box=True)
        before = repr(config)
        try:
            rendered = config.to_yaml()
            roundtrip &= Box.from_yaml(rendered).to_dict() == source
            with TemporaryDirectory() as root:
                target = Path(root) / 'nested.yaml'
                config.to_yaml(filename=target)
                files &= Box.from_yaml(filename=target).to_dict() == source
            unchanged &= repr(config) == before and config._box_config['frozen_box'] is True
            try:
                config['unexpected'] = 'mutation'
                frozen = False
            except BoxError:
                pass
        except Exception:
            roundtrip = files = False
    ordinary = Box({'a': [1, {'b': 2}]})
    return {'frozen_yaml_matrix': roundtrip, 'file_matrix': files,
        'source_not_mutated': unchanged, 'source_stays_frozen': frozen,
        'ordinary_yaml_json': Box.from_yaml(ordinary.to_yaml()).to_dict() == ordinary.to_dict()
            and Box.from_json(ordinary.to_json()).to_dict() == ordinary.to_dict()}


print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(Path(os.environ['PROJECT_CANDIDATE_ROOT']) / 'library'), **observations()}))
