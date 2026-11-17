"""固定双版制品的缓存准入及输入漂移回归。"""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('prepare_ci_runtime', Path(__file__).resolve().parents[2] / 'services/runtime/scripts/prepare-ci-runtime.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class PrepareRuntimeTests(unittest.TestCase):
    """使用小型合成制品核对缓存拒绝边界。"""

    def test_cache_requires_matching_source_artifact_report_and_complete_inputs(self):
        """损坏制品、错误来源、缺报告及源码漂移分别拒绝。@return None。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {'src/entry.ts': 'synthetic entry', 'src/compat.ts': 'synthetic compatibility',
                'scripts/build-runtime.ts': "const BRIDGE_SOURCES = ['src/entry.ts', 'scripts/build-runtime.ts'];\nconst bridgePaths = [...BRIDGE_SOURCES, 'src/compat.ts'];"}
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
            binary = root / 'ccrb-runtime'
            binary.write_bytes(b'synthetic')
            identity = {'bytes': 9, 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'source_sha256': 'a' * 64, 'image_sha256': 'b' * 64, 'image_bytes': 10}
            report = {'schema_version': 1, 'source': {'version': '2.1.293', 'sha256': identity['source_sha256']},
                'launcher': {'sha256': identity['sha256'], 'bytes': 9}, 'image': {'sha256': 'b' * 64, 'bytes': 10},
                'recipe': {'version': 10, 'bridge_sources': {name: hashlib.sha256(value.encode()).hexdigest() for name,value in files.items()}}}
            metadata = root / 'ccrb-runtime.manifest.json'
            metadata.write_text(json.dumps(report))
            with patch.object(prepare, 'PROJECT', root), patch.dict(prepare.SOURCES, {'2.1.293': identity}):
                prepare.verify(binary, '2.1.293')
                binary.write_bytes(b'corrupted')
                with self.assertRaisesRegex(ValueError, '制品身份'):
                    prepare.verify(binary, '2.1.293')
                binary.write_bytes(b'synthetic')
                report['source']['version'] = '2.1.280'
                metadata.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, '报告来源'):
                    prepare.verify(binary, '2.1.293')
                report['source']['version'] = '2.1.293'
                metadata.write_text(json.dumps(report))
                (root / 'src/entry.ts').write_text('changed input')
                with self.assertRaisesRegex(ValueError, '当前仓库不一致'):
                    prepare.verify(binary, '2.1.293')
                (root / 'src/entry.ts').write_text(files['src/entry.ts'])
                report['recipe']['bridge_sources'].pop('src/compat.ts')
                metadata.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, '当前仓库不一致'):
                    prepare.verify(binary, '2.1.293')
                metadata.unlink()
                with self.assertRaises(FileNotFoundError):
                    prepare.verify(binary, '2.1.293')
