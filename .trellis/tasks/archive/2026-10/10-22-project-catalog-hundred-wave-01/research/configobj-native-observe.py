"""用合成内存配置观察实际校验、默认、注释输出、merge与插值。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import configobj
from configobj import ConfigObj, flatten_errors, get_extra_values
from configobj.validate import Validator


SPEC = ['[service]', 'port = integer(min=1, max=65535)', 'enabled = boolean',
    'required = string(min=1)', 'workers = integer(min=1, default=2)']
VALID = ['[service]', 'port = 8000', 'enabled = false', 'required = orders']
INVALID = ['[service]', 'port = 0', 'enabled = maybe', 'extra = spare']


def validation() -> dict:
    """核真实转换、默认和写出策略。@return 类型与默认事实。"""
    ordinary = ConfigObj(VALID, configspec=SPEC)
    copied = ConfigObj(VALID, configspec=SPEC)
    first, second = ordinary.validate(Validator()), copied.validate(Validator(), copy=True)
    normal_text, copied_text = '\n'.join(ordinary.write()), '\n'.join(copied.write())
    return {'validation_converts_values_and_adds_default': first is True and second is True
            and ordinary['service']['port'] == 8000 and ordinary['service']['enabled'] is False
            and ordinary['service']['workers'] == 2,
        'ordinary_default_is_readable_but_not_written': 'workers' in ordinary['service'].defaults
            and 'workers =' not in normal_text,
        'copy_true_writes_default': 'workers' not in copied['service'].defaults and 'workers = 2' in copied_text}


def errors() -> dict:
    """核嵌套错误的实际路径和额外键生命周期。@return 失败与额外键事实。"""
    failed = ConfigObj(INVALID, configspec=SPEC)
    result = failed.validate(Validator(), preserve_errors=True)
    flattened = {(tuple(path), key): error for path, key, error in flatten_errors(failed, result)}
    exact = set(flattened) == {(('service',), 'enabled'), (('service',), 'port'), (('service',), 'required')}
    valid_extra = ConfigObj([*VALID, 'extra = spare'], configspec=SPEC)
    before = get_extra_values(valid_extra)
    accepted = valid_extra.validate(Validator())
    after = get_extra_values(valid_extra)
    return {'flattened_errors_keep_path_and_exception': exact
            and type(flattened[(('service',), 'port')]).__name__ == 'VdtValueTooSmallError'
            and type(flattened[(('service',), 'enabled')]).__name__ == 'VdtTypeError'
            and flattened[(('service',), 'required')] is False,
        'failed_mapping_is_truthy_but_not_true': bool(result) and result is not True,
        'extras_require_prior_validation': before == [] and after == [(('service',), 'extra')],
        'validation_does_not_reject_extra_keys': accepted is True and valid_extra['service']['extra'] == 'spare'}


def editing() -> dict:
    """核注释、Unicode和真实返回字节类型。@return 编辑输出事实。"""
    config = ConfigObj(['# bakery', '[service] # heading', '# purchase budget',
        'limit    =    2   # units', 'label = 茶'], encoding='utf-8')
    config['service']['limit'] = '3'
    lines = config.write()
    raw = b'\n'.join(lines)
    restored = ConfigObj(lines, encoding='utf-8')
    return {'comments_and_unicode_survive_value_edit': all(marker in raw.decode('utf-8')
            for marker in ('# bakery', '# heading', '# purchase budget', '# units', '茶'))
            and restored['service']['limit'] == '3' and restored['service']['label'] == '茶',
        'explicit_encoding_returns_byte_lines': bool(lines) and all(isinstance(line, bytes) for line in lines)}


def composition() -> dict:
    """对照递归覆盖、列表替换和读取时插值。@return 组合配置事实。"""
    config = ConfigObj({'service': {'host': 'old-db', 'port': '8000', 'labels': ['a', 'b']}})
    config.merge({'service': {'port': '9000', 'labels': ['c']}})
    interpolated = ConfigObj(['base = /srv', '[service]', 'root = %(base)s/orders'])
    before = interpolated['service']['root']
    interpolated['base'] = '/opt'
    after = interpolated['service']['root']
    written = '\n'.join(interpolated.write())
    return {'merge_recurses_and_replaces_lists': config['service']['host'] == 'old-db'
            and config['service']['port'] == '9000' and config['service']['labels'] == ['c'],
        'interpolation_is_resolved_at_read': before == '/srv/orders' and after == '/opt/orders',
        'write_preserves_interpolation_expression': 'root = %(base)s/orders' in written
            and interpolated['service']['root'] == '/opt/orders'}


def main() -> None:
    """输出当前任务明确要求的原生事实。@return None。"""
    task = sys.argv[1]
    fields = {'CO-U01': ('validation_converts_values_and_adds_default',),
        'CO-C01': ('ordinary_default_is_readable_but_not_written', 'copy_true_writes_default'),
        'CO-U02': ('flattened_errors_keep_path_and_exception', 'failed_mapping_is_truthy_but_not_true'),
        'CO-P01': ('extras_require_prior_validation', 'validation_does_not_reject_extra_keys', 'failed_mapping_is_truthy_but_not_true'),
        'CO-U03': ('comments_and_unicode_survive_value_edit', 'explicit_encoding_returns_byte_lines'),
        'CO-C02': ('comments_and_unicode_survive_value_edit', 'explicit_encoding_returns_byte_lines'),
        'CO-U04': ('merge_recurses_and_replaces_lists',),
        'CO-C03': ('interpolation_is_resolved_at_read', 'write_preserves_interpolation_expression')}
    if task in ('CO-U01', 'CO-C01'):
        facts = validation()
    elif task in ('CO-U02', 'CO-P01'):
        facts = errors()
    elif task in ('CO-U03', 'CO-C02'):
        facts = editing()
    else:
        facts = composition()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(configobj.__file__).resolve() == root / 'library/src/configobj/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
