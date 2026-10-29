"""公开验证文件源成功替换和错误时保留原值，不要求跨源事务。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import confuse
from confuse import Configuration, YamlSource


class ReloadTests(unittest.TestCase):
    """通过真实配置文件与公开入口观察结果。"""

    def test_deleted_overlay_key_falls_back_after_configuration_reload(self) -> None:
        """文件删除的键不能继续遮盖低优先级默认值。@return None。"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.yaml'
            path.write_text('obsolete: overlay\nretained: old\n')
            config = Configuration('public-reload-test', read=False)
            config.add({'obsolete': 'default', 'retained': 'default'})
            config.set_file(str(path))
            path.write_text('retained: new\n')
            config.reload()
            self.assertEqual(config['obsolete'].get(str), 'default')
            self.assertEqual(config['retained'].get(str), 'new')
            self.assertEqual(dict(config.sources[0]), {'retained': 'new'})

    def test_empty_file_and_optional_missing_file_clear_only_their_source(self) -> None:
        """合法空快照不保留旧值，缺失可选来源同样为空。@return None。"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.yaml'
            path.write_text('obsolete: old\n')
            source = YamlSource(str(path), optional=True)
            path.write_text('')
            source.load()
            self.assertEqual(dict(source), {})
            path.write_text('next: new\n')
            source.load()
            self.assertEqual(dict(source), {'next': 'new'})
            path.unlink()
            source.load()
            self.assertEqual(dict(source), {})

    def test_parse_and_nonmapping_errors_preserve_last_valid_mapping(self) -> None:
        """先解析并校验成功，才允许发布替换。@return None。"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.yaml'
            path.write_text('stable: value\n')
            source = YamlSource(str(path))
            for invalid in ('broken: [\n', '- not-a-mapping\n'):
                path.write_text(invalid)
                with self.assertRaises((confuse.ConfigError, TypeError)):
                    source.load()
                self.assertEqual(dict(source), {'stable': 'value'})

    def test_source_identity_metadata_and_dictionary_source_stay_unchanged(self) -> None:
        """替换映射内容不替换来源对象，也不重载普通字典。@return None。"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.yaml'
            path.write_text('first: one\n')
            source = YamlSource(str(path), default=True, base_for_paths=True)
            config = Configuration('public-reload-test', read=False)
            config.add(source)
            config.add({'dictionary': 'kept'})
            identity = config.sources[0]
            path.write_text('second: two\n')
            config.reload()
            self.assertIs(config.sources[0], identity)
            self.assertEqual(source.filename, str(path.resolve()))
            self.assertTrue(source.default)
            self.assertTrue(source.base_for_paths)
            self.assertEqual(dict(source), {'second': 'two'})
            self.assertEqual(config['dictionary'].get(str), 'kept')
