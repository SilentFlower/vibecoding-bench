"""用合成配置观察层级、类型、环境快照、脱敏和文件重载。"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import confuse
from confuse import Configuration, EnvSource, YamlSource


def configuration() -> Configuration:
    """创建不发现用户配置的独立对象。@return 空合成配置。"""
    return Configuration('synthetic-scenario', read=False)


def observe(identifier: str) -> dict:
    """运行当前任务的真实配置行为。@param identifier 稳定任务码。@return 实际事实。"""
    if identifier == 'CF-U01':
        config = configuration()
        config.add({'db': {'host': 'base', 'port': 5432}, 'workers': 1})
        config.set({'db': {'host': 'override'}})
        return {'priority_lookup_and_flatten_have_distinct_mapping_shapes':
            config['db'].get() == {'host': 'override'}
            and config['db']['port'].get(int) == 5432
            and config.flatten()['db'] == {'host': 'override', 'port': 5432}}
    if identifier == 'CF-C01':
        config = configuration()
        config.set({'fraction': 3.9, 'text': '3', 'flag': True})
        try:
            config['text'].get(int)
            rejects_text = False
        except confuse.ConfigError:
            rejects_text = True
        return {'integer_template_truncates_and_is_not_a_strict_integer_parser':
            config['fraction'].get(int) == 3 and config['flag'].get(int) is True and rejects_text}
    if identifier == 'CF-U02':
        with patch.dict(os.environ, {'SYNTH_DB__PORT': '5432', 'SYNTH_ITEMS__0': 'A',
                'SYNTH_ITEMS__1': 'B', 'SYNTH_PAYLOAD': '[A, B]'}, clear=True):
            config = configuration()
            config.set_env('SYNTH_')
            full = EnvSource('SYNTH_', parse_yaml_docs=True)
            initial = (config['db']['port'].get(int), config['items'].get(), config['payload'].get())
            os.environ['SYNTH_DB__PORT'] = '6000'
            config.reload()
            still_old = config['db']['port'].get(int)
            fresh = EnvSource('SYNTH_')
        return {'environment_overlay_is_typed_nested_and_not_refreshed_by_file_reload':
            initial == (5432, ['A', 'B'], '[A, B]') and full['payload'] == ['A', 'B']
            and still_old == 5432 and fresh['db']['port'] == 6000}
    if identifier == 'CF-C02':
        config = configuration()
        config.set({'auth': {'token': 'PUBLIC_SAMPLE'}, 'host': 'demo'})
        config['auth']['token'].redact = True
        masked, plain = config.flatten(redact=True), config.flatten()
        return {'redacted_projection_does_not_erase_raw_configuration':
            masked['auth']['token'] == 'REDACTED' and masked['host'] == 'demo'
            and config['auth']['token'].get(str) == 'PUBLIC_SAMPLE'
            and plain['auth']['token'] == 'PUBLIC_SAMPLE'}
    if identifier == 'CF-P01':
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / 'first.yaml', Path(directory) / 'second.yaml'
            first.write_text('first: old-A\n')
            second.write_text('second: old-B\n')
            config = configuration()
            config.add(YamlSource(str(first)))
            config.add(YamlSource(str(second)))
            first.write_text('first: new-A\n')
            second.write_text('broken: [\n')
            try:
                config.reload()
                failed = False
            except confuse.ConfigError:
                failed = True
            return {'reload_is_not_an_all_source_publication_transaction':
                failed and config['first'].get(str) == 'new-A' and config['second'].get(str) == 'old-B'}
    if identifier == 'CF-M01':
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'overlay.yaml'
            path.write_text('retired: old-overlay\nactive: old\n')
            config = configuration()
            defaults = {'retired': 'base', 'active': 'fallback'}
            config.add(defaults)
            config.set_file(str(path), base_for_paths=True)
            source = config.sources[0]
            path.write_text('active: new\n')
            config.reload()
            replaced = (config['retired'].get(str) == 'base' and config['active'].get(str) == 'new'
                and dict(source) == {'active': 'new'} and config.sources[0] is source
                and source.filename == str(path.resolve()) and source.base_for_paths)
            path.write_text('{}\n')
            config.reload()
            empty = dict(source) == {} and config['active'].get(str) == 'fallback'
            path.write_text('active: stable\n')
            source.load()
            retained = True
            for content in ('broken: [\n', '- item\n'):
                path.write_text(content)
                try:
                    source.load()
                    retained = False
                except (confuse.ConfigError, TypeError):
                    retained = retained and dict(source) == {'active': 'stable'}
            optional_path = Path(directory) / 'optional.yaml'
            optional_path.write_text('gone: value\n')
            optional = YamlSource(str(optional_path), optional=True)
            optional_path.unlink()
            optional.load()
            return {'file_reload_replaces_one_source_only_after_success':
                replaced and empty and retained and dict(optional) == {} and defaults == {'retired': 'base', 'active': 'fallback'}}
    raise ValueError('未知配置任务：' + identifier)


def main() -> None:
    """核候选源码并只输出当前任务事实。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(confuse.__file__).resolve() == root / 'library/confuse/__init__.py',
        **observe(sys.argv[1])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
