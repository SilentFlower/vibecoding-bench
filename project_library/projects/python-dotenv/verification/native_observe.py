"""在无凭据临时目录实际调用候选dotenv，区分程序事实与语义回答质量。"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


def observe(operation):
    """保留异常为失败观察。@param operation 单项调用。@return 调用值或异常。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


def api_facts(module):
    """核对映射与环境修改的真实差别。@param module 候选模块。@return 独立事实。"""
    text = 'BASE=file\nDERIVED=${BASE}/data\nEMPTY=\nBARE\n'
    initial = {'BASE': 'process', 'SYNTHETIC_KEEP': 'kept'}
    with patch.dict(os.environ, initial, clear=True):
        values = module.dotenv_values(stream=io.StringIO(text))
        untouched = dict(os.environ) == initial
        result = module.load_dotenv(stream=io.StringIO(text))
        default = dict(os.environ)
    with patch.dict(os.environ, initial, clear=True):
        override_result = module.load_dotenv(stream=io.StringIO(text), override=True)
        overridden = dict(os.environ)
    return {'mapping_only': values == {'BASE': 'file', 'DERIVED': 'file/data', 'EMPTY': '', 'BARE': None} and untouched,
        'default_environment': result is True and default == {**initial, 'DERIVED': 'process/data', 'EMPTY': ''},
        'override_environment': override_result is True and overridden == {'BASE': 'file', 'DERIVED': 'file/data', 'EMPTY': '', 'SYNTHETIC_KEEP': 'kept'}}


def merge_facts(module):
    """通过真实临时文件核有序合并而非伪造字典。@param module 候选。@return 事实。"""
    with TemporaryDirectory(prefix='de-merge-') as directory, patch.dict(os.environ, {'KEEP': 'outside'}, clear=True):
        a, b = Path(directory) / 'shared.env', Path(directory) / 'local.env'
        a.write_text('COLOR=shared\nSHARED=one\nEMPTY=\n', encoding='utf-8')
        b.write_text('COLOR=local\nLOCAL=two\n', encoding='utf-8')
        before = dict(os.environ)
        shared, local = module.dotenv_values(a), module.dotenv_values(b)
        deployment = {'COLOR': 'deployment', 'DEPLOYMENT': 'three'}
        merged = {**shared, **local, **deployment}
        return {'layers': merged == {'COLOR': 'deployment', 'SHARED': 'one', 'EMPTY': '', 'LOCAL': 'two', 'DEPLOYMENT': 'three'},
            'order_matters': {**shared, **local}['COLOR'] == 'local' and {**local, **shared}['COLOR'] == 'shared',
            'environment_unchanged': dict(os.environ) == before}


def startup_facts(module):
    """证明显式路径与应用验证边界。@param module 候选。@return 两工作目录及缺字段控制。"""
    with TemporaryDirectory(prefix='de-startup-') as directory, patch.dict(os.environ, {'APP_NAME': 'deployment'}, clear=True):
        base = Path(directory)
        config = base / 'synthetic.env'
        config.write_text('APP_NAME=local\nOPTIONAL=\n', encoding='utf-8')
        original_cwd = Path.cwd()
        observed = []
        try:
            for name in ('a', 'b'):
                cwd = base / name
                cwd.mkdir()
                os.chdir(cwd)
                merged = {**module.dotenv_values(config), **os.environ}
                observed.append(merged)
            missing = {**module.dotenv_values(base / 'missing.env'), **{}}
            marker = base / 'started'
            if missing.get('APP_NAME'):
                marker.write_text('started', encoding='utf-8')
        finally:
            os.chdir(original_cwd)
        return {'cwd_independent': observed == [{'APP_NAME': 'deployment', 'OPTIONAL': ''}] * 2,
            'missing_stops_application': not marker.exists(), 'missing_mapping': missing == {}}


def incident_facts(module):
    """仅作材料披露后的准入见证，不挂初始任务原生规则。@param module 候选。@return 三路对照。"""
    observations = []
    with TemporaryDirectory(prefix='de-incident-') as directory:
        target = Path(directory) / 'synthetic.env'
        target.write_text('APP_MODE=local\n', encoding='utf-8')
        for environment, override in (({'APP_MODE': 'deployment'}, False), ({'APP_MODE': 'deployment'}, True), ({}, False)):
            with patch.dict(os.environ, environment, clear=True):
                loaded = module.load_dotenv(target, override=override)
                observations.append((loaded, os.environ.get('APP_MODE')))
    return {'default_preserves_process': observations[0] == (True, 'deployment'),
        'override_control': observations[1] == (True, 'local'),
        'missing_process_control': observations[2] == (True, 'local')}


def cli_facts(module, root):
    """真实执行候选模块CLI并对照API、退出码和文件。@param module 候选。@param root 候选根。@return 观察。"""
    with TemporaryDirectory(prefix='de-cli-') as directory:
        target = Path(directory) / 'synthetic.env'
        target.write_text('EMPTY=\nOPTIONAL\nPRESENT=ready\n', encoding='utf-8')
        environment = {**os.environ, 'PYTHONPATH': str(root / 'library/src')}

        def invoke(*arguments):
            """只传明确临时路径，不使用cwd自动查找。@param arguments CLI参数。@return 完整进程。"""
            return subprocess.run([sys.executable, '-B', '-m', 'dotenv', '-f', str(target), *arguments],
                env=environment, cwd=directory, capture_output=True, text=True, timeout=5, check=False)

        values = module.dotenv_values(target)
        empty, bare, missing, present = [invoke('get', key) for key in ('EMPTY', 'OPTIONAL', 'ABSENT', 'PRESENT')]
        listed, simple = invoke('list', '--format=json'), invoke('list')
        return {'mapping_distinctions': values == {'EMPTY': '', 'OPTIONAL': None, 'PRESENT': 'ready'},
            'empty_success': empty.returncode == 0 and empty.stdout == '\n',
            'bare_and_missing_failure': bare.returncode != 0 and missing.returncode != 0,
            'normal_value': present.returncode == 0 and present.stdout == 'ready\n',
            'list_null': listed.returncode == 0 and json.loads(listed.stdout) == values,
            'simple_omits_bare': simple.returncode == 0 and simple.stdout == 'EMPTY=\nPRESENT=ready\n'}


def interpolation_facts(module):
    """核顺序插值、外部值和关闭选项。@param module 候选。@return 观察。"""
    with patch.dict(os.environ, {}, clear=True):
        forward = module.dotenv_values(stream=io.StringIO('A=${B}\nB=ready\nLITERAL=$B\n'))
        reverse = module.dotenv_values(stream=io.StringIO('B=ready\nA=${B}\nLITERAL=$B\n'))
        literal = module.dotenv_values(stream=io.StringIO('A=${B}\nLITERAL=$B\n'), interpolate=False)
    with patch.dict(os.environ, {'B': 'external'}, clear=True):
        external = module.dotenv_values(stream=io.StringIO('A=${B}\nB=ready\n'))
    return {'forward': forward == {'A': '', 'B': 'ready', 'LITERAL': '$B'},
        'reverse': reverse == {'B': 'ready', 'A': 'ready', 'LITERAL': '$B'},
        'disabled': literal == {'A': '${B}', 'LITERAL': '$B'},
        'external': external == {'A': 'external', 'B': 'ready'}}


def default_facts(module):
    """冻结空值默认现状，防止借新题改变全局兼容。@param module 候选。@return 观察。"""
    with patch.dict(os.environ, {}, clear=True):
        outputs = [module.dotenv_values(stream=io.StringIO(prefix + 'A=${B:-d}\n'))['A']
            for prefix in ('', 'B=\n', 'B\n', 'B=ready\n')]
        literal = module.dotenv_values(stream=io.StringIO('B=\nA=${B:-d}\n'), interpolate=False)
    return {'missing_empty_bare_nonempty': outputs == ['d', '', '', 'ready'],
        'literal': literal == {'B': '', 'A': '${B:-d}'}}


def policy_facts(module):
    """只对指定字段应用业务政策，核文件和环境不变。@param module 候选。@return 观察。"""
    outputs, unchanged = [], True
    with TemporaryDirectory(prefix='de-policy-') as directory, patch.dict(os.environ, {'KEEP': 'outside'}, clear=True):
        target = Path(directory) / 'policy.env'
        for prefix in ('', 'REGION\n', 'REGION=\n', 'REGION=west\n'):
            content = (prefix + 'OTHER_EMPTY=\nREGION_LABEL=${REGION}/app\n').encode()
            target.write_bytes(content)
            environment = dict(os.environ)
            values = module.dotenv_values(target, interpolate=False)
            region = values.get('REGION')
            region = 'local' if region is None or region == '' else region
            outputs.append((region, region + '/app', values['OTHER_EMPTY']))
            unchanged = unchanged and target.read_bytes() == content and dict(os.environ) == environment
    return {'field_policy': outputs == [('local', 'local/app', '')] * 3 + [('west', 'west/app', '')],
        'source_and_environment_unchanged': unchanged}


def newline_facts(module):
    """核非目标原字节及目标LF，包含真实文件与语义读回。@param module 候选。@return 矩阵。"""
    results = {}
    for name, newline in (('crlf', b'\r\n'), ('lf', b'\n'), ('cr', b'\r')):
        for operation in ('replace', 'append', 'unset'):
            with TemporaryDirectory(prefix='de-newline-') as directory:
                target = Path(directory) / 'synthetic.env'
                before = b'# untouched' + newline + newline + b'KEEP="first' + newline + b'second"' + newline
                original = before + b'COLOR=old' + newline if operation != 'append' else before
                target.write_bytes(original)
                target.chmod(0o640)
                if operation == 'unset':
                    returned = module.unset_key(target, 'COLOR')
                    expected = before
                    value_ok = 'COLOR' not in module.dotenv_values(target)
                    return_ok = returned == (True, 'COLOR')
                else:
                    returned = module.set_key(target, 'COLOR', 'new')
                    expected = before + (b'\n' if operation == 'append' and newline == b'\r' else b'') + b"COLOR='new'\n"
                    value_ok = module.get_key(target, 'COLOR') == 'new'
                    return_ok = returned == (True, 'COLOR', 'new')
                results[f'{name}_{operation}'] = target.read_bytes() == expected and value_ok and return_ok and stat.S_IMODE(target.stat().st_mode) == 0o640
    with TemporaryDirectory(prefix='de-mixed-') as directory:
        target = Path(directory) / 'mixed.env'
        prefix = b'# comment\r\n\rA=one\nB="two\r\nlines"\r'
        target.write_bytes(prefix + b'COLOR=old\n')
        module.set_key(target, 'COLOR', 'new', quote_mode='never')
        results['mixed_records'] = target.read_bytes() == prefix + b'COLOR=new\n'
        target.write_bytes(b'# tail without newline')
        module.set_key(target, 'COLOR', 'new')
        results['append_separator'] = target.read_bytes() == b"# tail without newline\nCOLOR='new'\n"
        target.write_bytes(b'A=1\r\nCOLOR=one\r\nCOLOR=two\r\nB=2\r\n')
        module.set_key(target, 'COLOR', 'new')
        results['duplicate_targets'] = target.read_bytes() == b"A=1\r\nCOLOR='new'\nCOLOR='new'\nB=2\r\n"
    return results


def newline_baseline(module):
    """记录原版格式变化及正常LF对照。@param module 候选。@return 观察。"""
    with TemporaryDirectory(prefix='de-before-') as directory:
        path = Path(directory) / 'synthetic.env'
        before = b'# untouched\r\nKEEP="first\r\nsecond"\r\nCOLOR=old\r\n'
        path.write_bytes(before)
        semantic = module.dotenv_values(path)
        module.set_key(path, 'COLOR', 'new')
        after = path.read_bytes()
        return {'original_normalizes_non_targets': after == b"# untouched\nKEEP=\"first\nsecond\"\nCOLOR='new'\n",
            'untouched_value_same': module.dotenv_values(path)['KEEP'] == semantic['KEEP'],
            'lf_control': newline_facts(module)['lf_replace']}


def key_facts(module):
    """核拒绝发生在rewrite前，不能靠写后恢复伪造。@param module 候选。@return 独立矩阵。"""
    import dotenv.main as main_module

    results = {}
    for label, key in (('lf', 'REPORT\nREGION'), ('cr', 'REPORT\rREGION'), ('crlf', 'REPORT\r\nREGION')):
        for present in (True, False):
            with TemporaryDirectory(prefix='de-key-') as directory:
                target = Path(directory) / 'synthetic.env'
                original = b'# kept\r\nCOLOR=blue\r\n'
                if present:
                    target.write_bytes(original)
                listing = sorted(Path(directory).iterdir())
                with patch.object(main_module, 'rewrite', wraps=main_module.rewrite) as rewrite:
                    raised = False
                    try:
                        module.set_key(target, key, 'ready')
                    except ValueError:
                        raised = True
                    untouched = target.read_bytes() == original if present else not target.exists()
                    results[f'{label}_{"existing" if present else "missing"}'] = raised and not rewrite.called and untouched and sorted(Path(directory).iterdir()) == listing
    with TemporaryDirectory(prefix='de-normal-') as directory:
        target = Path(directory) / 'normal.env'
        normal = True
        for key in ('REPORT_REGION', 'REPORT.REGION', 'REPORT-REGION', '区域'):
            returned = module.set_key(target, key, "a'quoted\\path\nnext")
            normal = normal and returned == (True, key, "a'quoted\\path\nnext") and module.get_key(target, key) == "a'quoted\\path\nnext"
        results['normal_keys_and_multiline_values'] = normal
    return results


def key_baseline(module):
    """在临时文件复现writer与parser不一致。@param module 候选。@return 原版及正常对照。"""
    results = {}
    with TemporaryDirectory(prefix='de-key-before-') as directory:
        for label, key in (('lf', 'REPORT\nREGION'), ('cr', 'REPORT\rREGION')):
            target = Path(directory) / (label + '.env')
            target.write_bytes(b'COLOR=blue\n')
            result = module.set_key(target, key, 'ready')
            results[label] = result == (True, key, 'ready') and module.get_key(target, key) is None and target.read_bytes() != b'COLOR=blue\n'
        target = Path(directory) / 'normal.env'
        module.set_key(target, 'REPORT_REGION', 'ready')
        results['normal_roundtrip'] = module.get_key(target, 'REPORT_REGION') == 'ready'
    return results


def main() -> None:
    """读取固定模式并核真实导入候选实现。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['api', 'merge', 'startup', 'cli', 'interpolation', 'defaults', 'policy', 'newline', 'newline-baseline', 'keys', 'keys-baseline', 'incident'])
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    options = parser.parse_args()
    root = options.candidate_root.resolve()
    sys.path.insert(0, str(root / 'library/src'))
    import dotenv

    imported = Path(dotenv.__file__).resolve().is_relative_to(root / 'library/src/dotenv')
    operations = {'api': api_facts, 'merge': merge_facts, 'startup': startup_facts,
        'incident': incident_facts, 'cli': lambda module: cli_facts(module, root), 'interpolation': interpolation_facts,
        'defaults': default_facts, 'policy': policy_facts, 'newline': newline_facts,
        'newline-baseline': newline_baseline, 'keys': key_facts, 'keys-baseline': key_baseline}
    result = observe(lambda: operations[options.mode](dotenv))
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
