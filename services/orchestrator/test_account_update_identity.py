"""账号镜像来源沿原镜像命名合同支持手工批次，签名发行合同独立。"""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_update_identity import image_origin, save_image_origin
from runtime_files import atomic_json


class ImageOriginTests(unittest.TestCase):
    """真实私有来源文件的保存与读回。"""

    def test_custom_batch_round_trip_keeps_exact_image_and_role(self) -> None:
        """已支持的手工批次可读回，错误角色、批次及摘要继续拒绝。:return: None。"""
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'V3_UPDATE_GATE_DIR': folder}):
            root = Path(folder)
            release = 'manual-20261118'
            reference = 'ghcr.io/silentflower/flower2api-account:v3-' + release
            image = SimpleNamespace(attrs={'Id': 'sha256:' + 'a' * 64, 'Config': {'Labels': {
                'vibebench.product': 'v3', 'vibebench.role': 'account', 'vibebench.release': release,
                'vibebench.account-runtime-protocol': '1', 'vibebench.system-update-protocol': '1'}}})
            runtime = SimpleNamespace(image=reference, release_id=release, client=Mock(), _root=lambda row: root)
            runtime.client.images.get.return_value = image
            row = {'environment_id': 'e' * 32}
            save_image_origin(runtime, row)
            original = image_origin(runtime, row)
            self.assertEqual(reference, original['reference'])
            self.assertEqual(release, original['release'])
            atomic_json(root / 'runtime/account-image.json', {**original, 'reference': reference.removeprefix('ghcr.io/silentflower/')})
            self.assertEqual(release, image_origin(runtime, row)['release'])
            for change in ({'reference': reference.replace('-account:', '-control:')},
                    {'release': 'another'}, {'image_id': 'unknown'}, {'release': '../escape'}):
                atomic_json(root / 'runtime/account-image.json', {**original, **change})
                with self.subTest(change=change), self.assertRaises(ValueError):
                    image_origin(runtime, row)
