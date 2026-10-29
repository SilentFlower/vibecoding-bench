"""TLS 抓包公开边界测试：使用合成握手行，不访问外部服务。"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import capture_artifacts
from capture_artifacts import capture_file_preview, capture_summary


def clienthello_record(connection: str = 'client-1') -> dict:
    """生成带嵌套敏感 canary 的 schema 1 行，验证公开白名单。

    :param connection: 合成客户端连接标识。
    :return: 仅供测试使用的私有握手行。
    """
    canary = 'PRIVATE_TLS_CANARY'
    return {'schema': 1, 'event': 'tls_clienthello', 'ts': 1.5, 'direction': 'client_to_recorder',
        'transport': 'tcp', 'client_connection_id': connection, 'parse_status': 'ok',
        'parse_error': canary, 'capture_scope': 'all', 'target_status': 'target',
        'capture_context_status': 'ok', 'capture_context_error': canary,
        'capture_context': {'schema': 1, 'source': 'run:fixture:1', 'run_id': 'fixture',
            'claude_code_version': '2.1.303', 'claude_code_version_source': 'explicit', 'private': canary},
        'legacy_version': 769, 'cipher_suites': [4, 5, 10, 9, 100, 98, 3, 6, 19, 18, 99],
        'extensions': [{'type': 51, 'length': 36, 'data_base64': canary, 'unknown': {'ticket': canary}}],
        'signature_algorithms': [2052, 1027], 'supported_groups': [29, 23], 'supported_versions': [772, 771],
        'ec_point_formats': [0], 'key_share': [{'group': 29, 'key_exchange_length': 32, 'key_bytes': canary}],
        'sni': 'api.anthropic.com', 'alpn_protocols': [{'text': 'h2', 'base64': canary, 'ticket': canary}],
        'ja3': {'string': '769,4-5-10-9-100-98-3-6-19-18-99,,,',
            'md5': 'de350869b8c85de67a350c8d186f11e6', 'psk': canary},
        'raw_format': 'clienthello_body', 'raw_base64': canary, 'raw_sha256': canary,
        'session_id': canary, 'ticket': {'identity': canary}, 'unknown': {'binder': canary}}


class TlsCaptureArtifactsTests(unittest.TestCase):
    """确保聚合、单文件预览、历史兼容及扫描预算使用同一安全合同。"""

    def setUp(self) -> None:
        """创建私有合成证据目录。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'capture'
        self.base.mkdir()

    def write(self, record: dict | None = None, relative: str = 'tls_clienthello.jsonl') -> Path:
        """追加合成 JSONL。:param record: 私有行。:param relative: 组内路径。:return: 写入文件。"""
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as stream:
            stream.write(json.dumps(record or clienthello_record()) + '\n')
        return path

    def test_summary_and_preview_rebuild_nested_whitelist(self) -> None:
        """原始字节、未知字段与任意异常文本不能通过任一公开读取方式。:return: None。"""
        self.write()
        summary = capture_summary(self.base)
        preview = capture_file_preview(self.base, 'tls_clienthello.jsonl')
        self.assertEqual(summary['tls_clienthello'], preview)
        self.assertEqual('complete', preview['status'])
        self.assertTrue(preview['count_exact'])
        self.assertEqual(1, preview['total_records'])
        self.assertEqual('partial', summary['status'])
        self.assertFalse(summary['index_available'])
        public = preview['entries'][0]
        self.assertEqual({'type': 51, 'length': 36}, public['extensions'][0])
        self.assertEqual({'group': 29, 'key_exchange_length': 32}, public['key_share'][0])
        self.assertEqual([{'text': 'h2'}], public['alpn_protocols'])
        self.assertEqual('2.1.303', public['capture_context']['claude_code_version'])
        self.assertEqual('de350869b8c85de67a350c8d186f11e6', public['ja3']['md5'])
        self.assertNotIn('PRIVATE_TLS_CANARY', json.dumps(summary))
        for forbidden in ('raw_base64', 'raw_sha256', 'session_id', 'ticket', 'unknown', 'parse_error', 'capture_context_error'):
            self.assertNotIn(forbidden, public)

    def test_legacy_missing_and_linked_evidence_remain_unavailable(self) -> None:
        """旧目录没有 TLS 是兼容状态，文件或父目录链接均不能提供新预览。:return: None。"""
        original = capture_summary(self.base)
        self.assertEqual('unavailable', original['tls_clienthello']['status'])
        self.assertFalse(original['tls_clienthello']['available'])
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'tls_clienthello.jsonl').write_text(json.dumps(clienthello_record()) + '\n')
        (self.base / 'tls_clienthello.jsonl').symlink_to(outside / 'tls_clienthello.jsonl')
        (self.base / 'executions').mkdir()
        (self.base / 'executions/linked').symlink_to(outside, target_is_directory=True)
        value = capture_summary(self.base)
        self.assertFalse(value['tls_clienthello']['available'])
        self.assertEqual([], value['files'])
        for relative in ('tls_clienthello.jsonl', 'executions/linked/tls_clienthello.jsonl',
                '../outside/tls_clienthello.jsonl', str(outside / 'tls_clienthello.jsonl'), 'http_capture.jsonl', 'capture.flow'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                capture_file_preview(self.base, relative)

    def test_partial_malformed_and_recursive_lines_return_fixed_status(self) -> None:
        """追加中半行、坏 JSON 和深层数据不泄漏原文，已落盘的有效行仍可读取。:return: None。"""
        path = self.write()
        with path.open('a') as stream:
            stream.write('PRIVATE_TLS_CANARY\n' + '[' * 2000 + '0' + ']' * 2000 + '\n')
            stream.write('{"raw_base64":"PRIVATE_TLS_CANARY"')
        value = capture_file_preview(self.base, path.name)
        self.assertEqual('partial', value['status'])
        self.assertEqual(1, value['scanned_records'])
        self.assertFalse(value['count_exact'])
        self.assertIsNone(value['total_records'])
        self.assertEqual(['incomplete_line', 'invalid_record'], value['issues'])
        self.assertNotIn('PRIVATE_TLS_CANARY', json.dumps(value))

    def test_group_budgets_are_shared_across_executions(self) -> None:
        """多代文件共用字节、记录和行数预算，超预算计数明确不是全量。:return: None。"""
        for index in range(3):
            self.write(clienthello_record(f'client-{index}'), f'executions/{index}/tls_clienthello.jsonl')
        line_bytes = (self.base / 'executions/0/tls_clienthello.jsonl').stat().st_size
        for options, expected in (({'TLS_PREVIEW_MAX_RECORDS': 2}, 2),
                ({'TLS_PREVIEW_MAX_BYTES': line_bytes + 10}, 1), ({'TLS_PREVIEW_MAX_LINES': 1}, 1)):
            with self.subTest(options=options), patch.multiple(capture_artifacts, **options):
                value = capture_summary(self.base)['tls_clienthello']
            self.assertTrue(value['truncated'])
            self.assertFalse(value['count_exact'])
            self.assertIsNone(value['total_records'])
            self.assertEqual(expected, value['scanned_records'])
            self.assertLessEqual(value['bytes_read'], options.get('TLS_PREVIEW_MAX_BYTES', capture_artifacts.TLS_PREVIEW_MAX_BYTES))
        with patch.object(capture_artifacts, 'TLS_PREVIEW_MAX_LINE_BYTES', 128):
            value = capture_summary(self.base)['tls_clienthello']
        self.assertIn('line_limit', value['issues'])
        self.assertTrue(value['truncated'])
        self.assertEqual([], value['entries'])

    def test_malformed_nested_types_and_unreadable_files_do_not_escape(self) -> None:
        """白名单字段也须校验类型，损坏行或文件错误不能抛出原始异常。:return: None。"""
        record = clienthello_record()
        record['signature_algorithms'] = [{'binder': 'PRIVATE_TLS_CANARY'}, True, 2052]
        record['key_share'].append({'group': 29, 'key_exchange_length': {'raw': 'PRIVATE_TLS_CANARY'}})
        record['ja3']['md5'] = 'a' * 32
        self.write(record)
        value = capture_summary(self.base)['tls_clienthello']
        self.assertEqual('partial', value['status'])
        self.assertEqual([2052], value['entries'][0]['signature_algorithms'])
        self.assertIsNone(value['entries'][0]['ja3'])
        self.assertTrue(value['entries'][0]['fields_incomplete'])
        self.assertNotIn('PRIVATE_TLS_CANARY', json.dumps(value))
        with patch.object(capture_artifacts.os, 'open', side_effect=PermissionError('/private/PRIVATE_TLS_CANARY')):
            value = capture_summary(self.base)['tls_clienthello']
        self.assertEqual(['unreadable_file'], value['issues'])
        self.assertNotIn('PRIVATE_TLS_CANARY', json.dumps(value))

    def test_absent_vectors_and_legal_empty_key_share_stay_distinct(self) -> None:
        """未知或缺失字段保留 null，合法空 key_share 不被报告为解析失败。:return: None。"""
        record = clienthello_record()
        record.update(key_share=[], supported_groups=None, alpn_protocols=None)
        self.write(record)
        value = capture_summary(self.base)['tls_clienthello']
        self.assertEqual('complete', value['status'])
        self.assertEqual([], value['entries'][0]['key_share'])
        self.assertIsNone(value['entries'][0]['supported_groups'])
        self.assertIsNone(value['entries'][0]['alpn_protocols'])

    def test_missing_fingerprint_does_not_claim_complete_parse(self) -> None:
        """被截减但仍可解析的 JSON 行缺少必要指纹时，只能报告不完整。:return: None。"""
        record = clienthello_record()
        record.pop('ja3')
        self.write(record)
        value = capture_summary(self.base)['tls_clienthello']
        self.assertEqual('partial', value['status'])
        self.assertTrue(value['entries'][0]['fields_incomplete'])

    def test_shared_renderer_displays_fingerprint_and_escapes_connection_fields(self) -> None:
        """实际共用渲染函数显示指纹和连接，并转义动态内容；不依赖浏览器替身 DOM。:return: None。"""
        self.write()
        value = capture_summary(self.base)
        value['index']['entries'] = [{'flow_id': 'http-flow', 'client_connection_id': '<img src=x onerror=1>'}]
        value['tls_clienthello']['entries'][0]['client_connection_id'] = '<img src=x onerror=1>'
        script = '''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function renderCaptureTls(');
const end = source.indexOf('/**\\n * 按当前详情请求', start);
const utilsStart = source.indexOf('function escapeHTML(');
const utilsEnd = source.indexOf('// ===================== chrome', utilsStart);
if ([start, end, utilsStart, utilsEnd].some(position => position < 0)) throw new Error('渲染入口未找到');
const context = {};
vm.runInNewContext(source.slice(utilsStart, utilsEnd) + source.slice(start, end), context);
const capture = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify([context.renderCaptureDetail(capture), context.renderCaptureDetail({available:false})]));
'''
        result = subprocess.run(['node', '-e', script, str(Path(__file__).resolve().parents[1] / 'webui/app.js')],
            input=json.dumps(value), text=True, capture_output=True, check=True, timeout=10)
        html, legacy = json.loads(result.stdout)
        self.assertIn('TLS ClientHello', html)
        self.assertIn('de350869b8c85de67a350c8d186f11e6', html)
        self.assertIn('客户端连接', html)
        self.assertIn('&lt;img src=x onerror=1&gt;', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('PRIVATE_TLS_CANARY', html)
        self.assertIn('该抓包尚未保存 ClientHello 记录', legacy)


if __name__ == '__main__':
    unittest.main()
