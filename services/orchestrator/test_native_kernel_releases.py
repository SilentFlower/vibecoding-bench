"""固定发行源发现的有界投影、缓存与失败降级验证。"""
import copy
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import native_kernel_releases as releases
from native_sender import ASSET, VERSION


def release(number, **fields):
    """建立合成发行元数据。@param number beta序号。@param fields 覆盖字段。@return API条目。"""
    return {'tag_name': f'v0.1.0-beta.{number}', 'draft': False, 'published_at': '2026-11-13T00:00:00Z',
        'assets': [{'name': name} for name in (ASSET, 'runtime-release.json', 'runtime-release.sig')], **fields}


class ReleaseDiscoveryTests(unittest.TestCase):
    """发现与制品授信分别验证。"""

    def setUp(self):
        """每例清空缓存。@return 无。"""
        for name, value in (('_cache', None), ('_expires', 0)):
            current = patch.object(releases, name, value)
            current.start()
            self.addCleanup(current.stop)

    def test_projection_filters_drafts_invalid_tags_and_missing_or_duplicate_assets(self):
        """仅返回受控字段，按数字排序且拒绝缺失与重复附件。@return 无。"""
        data = [release(2), release(10, body='synthetic-secret'), release(9, draft=True),
            release(4, tag_name='https://invalid.example'), release(3, assets=[]), None]
        duplicate = release(7)
        duplicate['assets'].append({'name': ASSET})
        data.append(duplicate)
        result = releases.parse_releases(data)
        self.assertEqual([item['release'] for item in result], ['v0.1.0-beta.10', 'v0.1.0-beta.2'])
        self.assertEqual(set(result[0]), {'release', 'published_at'})
        for invalid in ({}, [None] * 101):
            with self.assertRaises(ValueError):
                releases.parse_releases(invalid)

    def test_cache_copies_and_failed_refresh_preserves_stale_choices(self):
        """并发调用者的对象独立，显式刷新失败显示旧采样时刻。@return 无。"""
        versions = releases.parse_releases([release(6)])
        with patch.object(releases, 'fetch_releases', return_value=versions) as fetch:
            first = releases.discover_releases()
            expected = copy.deepcopy(first)
            first['versions'].clear()
            self.assertEqual(releases.discover_releases(), expected)
            fetch.assert_called_once()
        with patch.object(releases, 'fetch_releases', side_effect=HTTPError(releases.API, 429, 'private', {}, None)):
            stale = releases.discover_releases(True)
        self.assertEqual(stale['state'], 'stale')
        self.assertEqual(stale['reason'], 'release_rate_limited')
        self.assertEqual(stale['checked_at_ms'], expected['checked_at_ms'])
        self.assertEqual(stale['versions'], versions)

    def test_uncached_failure_is_safe_and_explicit(self):
        """失败原因白名单投影，内置版始终存在。@return 无。"""
        with patch.object(releases, 'fetch_releases', side_effect=OSError('synthetic-secret')):
            result = releases.discover_releases()
        self.assertEqual((result['state'], result['versions']), ('unavailable', []))
        self.assertEqual(result['builtin']['release'], VERSION)
        self.assertNotIn('synthetic-secret', str(result))

    def test_fetch_uses_fixed_source_and_caps_body(self):
        """网络边界固定来源，有界响应拒绝超限内容。@return 无。"""
        with patch.object(releases.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = io.BytesIO(json.dumps([release(6)]).encode())
            self.assertEqual(releases.fetch_releases()[0]['release'], 'v0.1.0-beta.6')
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, releases.API)
            factory.return_value.open.return_value = io.BytesIO(b' ' * (releases.LIMIT + 1))
            with self.assertRaises(ValueError):
                releases.fetch_releases()
