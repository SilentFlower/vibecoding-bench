"""在实际候选上构建C扩展，分别观察C和纯Python的真实JSON业务行为。"""
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def runtime_control():
    """加载本项目冻结的可信构建和接线检查器。@return 控制模块。"""
    specification = spec_from_file_location('_bench_simplejson_control', Path(__file__).with_name('native_regression.py'))
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def build_source(root: Path) -> dict:
    """仅在产品已有/work运行副本构建实际候选。@param root 真实候选副本。@return 构建证据。"""
    evidence = Path('/work/simplejson-business-build')
    evidence.mkdir()
    control = runtime_control()
    return control._build_native_extension(root / 'library', control.SUITES['simplejson'],
        dict(os.environ), evidence, 15)


def tool(mode: str, arguments: list[str], data: bytes | None = None):
    """以真实CLI入口运行指定引擎。@param mode 引擎。@param arguments CLI参数。@param data 标准输入。@return 实际进程。"""
    code = ('import simplejson\n' + ('simplejson._toggle_speedups(False)\n' if mode == 'python' else '')
        + 'from simplejson.tool import main\nmain()\n')
    return subprocess.run([sys.executable, '-I', '-B', '-c', code, *arguments], input=data,
        capture_output=True, timeout=10)


def observe(identifier: str, mode: str, library) -> dict:
    """通过当前引擎运行一个独立业务目标。@param identifier 任务码。@param mode 引擎。@param library 实际模块。@return 事实。"""
    if identifier == 'SJ-U01':
        text = '{"amount":1.2300}'
        ordinary = library.loads(text)['amount']
        precise = library.loads(text, use_decimal=True)['amount']
        encoded = library.dumps({'amount': precise}, use_decimal=True)
        restored = library.loads(encoded, use_decimal=True)['amount']
        return {'explicit_decimal_mode_preserves_local_money_representation':
            isinstance(ordinary, float) and isinstance(precise, Decimal)
            and precise.as_tuple().exponent == -4 and '1.2300' in encoded
            and restored.as_tuple() == precise.as_tuple()}
    if identifier == 'SJ-C01':
        value = {'invoice': 9007199254740993, 'small': 5}
        numeric = library.loads(library.dumps(value))
        strings = library.loads(library.dumps(value, bigint_as_string=True))
        return {'large_integer_string_policy_changes_wire_type_without_changing_small_integers':
            type(numeric['invoice']) is int and numeric['invoice'] == value['invoice']
            and strings == {'invoice': '9007199254740993', 'small': 5}
            and type(strings['small']) is int}
    if identifier == 'SJ-C02':
        try:
            library.dumps([float('nan')])
            strict_encode = False
        except ValueError:
            strict_encode = True
        try:
            library.loads('NaN')
            strict_decode = False
        except ValueError:
            strict_decode = True
        return {'nonfinite_extensions_are_explicit_and_null_replacement_loses_information':
            strict_encode and strict_decode and library.dumps([float('nan')], allow_nan=True) == '[NaN]'
            and math.isnan(library.loads('NaN', allow_nan=True))
            and library.loads(library.dumps([float('nan')], ignore_nan=True)) == [None]}
    if identifier == 'SJ-U02':
        def unique(pairs):
            """按实际对象对检查重复键。@param pairs 原始键值对。@return 唯一映射。"""
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('synthetic duplicate key: ' + key)
                result[key] = value
            return result

        text = '{"qty":1,"qty":2}'
        errors = 0
        for duplicate in (text, '{"line":{"qty":1,"qty":2}}'):
            try:
                library.loads(duplicate, object_pairs_hook=unique)
            except ValueError:
                errors += 1
        return {'default_duplicate_keys_are_last_wins_and_pairs_hook_can_reject_them':
            library.loads(text) == {'qty': 2} and errors == 2
            and library.loads('{"qty":2}', object_pairs_hook=unique) == {'qty': 2}}
    if identifier == 'SJ-U03':
        text = '{"batch":1} {"batch":2}'
        try:
            library.loads(text)
            rejects_stream = False
        except ValueError:
            rejects_stream = True
        decoder = library.JSONDecoder()
        first, end = decoder.raw_decode(text)
        second, final = decoder.raw_decode(text, idx=end)
        prefix, boundary = decoder.raw_decode('{"batch":1}trailing-garbage')
        return {'raw_decode_returns_one_value_boundary_and_does_not_validate_the_whole_stream':
            rejects_stream and first == {'batch': 1} and end == 11
            and second == {'batch': 2} and final == len(text)
            and prefix == {'batch': 1} and boundary == 11}
    if identifier == 'SJ-P01':
        value = library.loads('{"sku":"","qty":-2}')
        return {'json_syntax_acceptance_does_not_validate_the_business_schema':
            value == {'sku': '', 'qty': -2}}
    if identifier == 'SJ-M01':
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid, output = root / 'bad.json', root / 'out.json'
            invalid.write_text('{"broken":')
            output.write_bytes(b'KEEP_OUTPUT\n')
            rejected = tool(mode, [str(invalid), str(output)])
            preserved = rejected.returncode != 0 and output.read_bytes() == b'KEEP_OUTPUT\n'
            same = root / 'same.json'
            same.write_text('{"z":2,"amount":1.2300}')
            formatted = tool(mode, [str(same), str(same)])
            inplace = (formatted.returncode == 0 and same.read_text().endswith('\n')
                and library.loads(same.read_text(), use_decimal=True) == {'z': 2, 'amount': Decimal('1.2300')})
            ordinary = tool(mode, [], b'{"b":2,"a":1}')
            return {'cli_parses_before_opening_output_and_allows_inplace_formatting':
                preserved and inplace and ordinary.returncode == 0
                and ordinary.stdout == b'{\n    "a": 1,\n    "b": 2\n}\n'}
    raise ValueError('未知JSON任务：' + identifier)


def main() -> None:
    """冻结候选构建后分别运行两引擎，不借安装库或混合结果放行。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    if sys.argv[1] == '--mode':
        import simplejson

        mode, identifier = sys.argv[2:]
        if mode == 'python':
            simplejson._toggle_speedups(False)
        valid = (Path(simplejson.__file__).resolve() == root / 'library/simplejson/__init__.py'
            and runtime_control()._simplejson_mode(root / 'library', mode))
        print(json.dumps({'candidate_import': valid, **observe(identifier, mode, simplejson)}, ensure_ascii=False))
        return
    build_source(root)
    observations = []
    for mode in ('c', 'python'):
        result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__)), '--mode', mode, sys.argv[1]],
            capture_output=True, text=True, check=True, timeout=15)
        observations.append(json.loads(result.stdout))
    if observations[0].keys() != observations[1].keys():
        raise ValueError('两种实际引擎的观察字段不一致')
    print(json.dumps({key: all(row[key] is True for row in observations) for key in observations[0]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
