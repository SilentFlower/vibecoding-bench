"""通过模板命中与淘汰行为验证缓存，不限定私有字段名称。"""
import asyncio
import json
import os
from pathlib import Path
import sys


def main() -> None:
    """核对有限缓存、版本快照与真实异步加载。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    sys.path.insert(0, str(root / 'library'))
    import liquid
    checks = dict.fromkeys(('versioned_loader_cache', 'versioned_loader_versions', 'versioned_loader_async'), False)
    try:
        from liquid import Environment
        from liquid.versioned_loader import VersionedDictLoader
        loader = VersionedDictLoader({'x': 'old', 'y': 'y'}, capacity=1)
        environment = Environment(loader=loader)
        snapshot = loader.snapshot()
        first = environment.get_template('x')
        hit = environment.get_template('x') is first
        environment.get_template('y')
        # 以实际重新编译确认淘汰，不读候选实现的内部缓存容器。
        evicted = environment.get_template('x') is not first
        lru = Environment(loader=VersionedDictLoader({'a': 'a', 'b': 'b', 'c': 'c'}, capacity=2))
        a, b = lru.get_template('a'), lru.get_template('b')
        lru.get_template('a')
        lru.get_template('c')
        checks['versioned_loader_cache'] = hit and evicted and lru.get_template('a') is a and lru.get_template('b') is not b
        loader.update('x', 'new')
        checks['versioned_loader_versions'] = snapshot['x'] == 'old' and first.render() == 'old'

        async def load() -> bool:
            """执行真实异步入口，检查更新后的完整模板。:return: 是否加载新版本。"""
            return (await environment.get_template_async('x')).render() == 'new'

        checks['versioned_loader_async'] = asyncio.run(load())
    except Exception:
        pass
    codes = [name for name, passed in checks.items() if not passed]
    print(json.dumps({'candidate_import': Path(liquid.__file__).resolve().is_relative_to(root / 'library'),
        'business': not codes, 'feedback_codes': codes}))


if __name__ == '__main__':
    main()
