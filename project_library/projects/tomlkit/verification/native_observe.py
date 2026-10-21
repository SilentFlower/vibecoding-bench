"""隔离执行真实 TOMLKit API，以独立预期核对业务事实及回答示例。"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import operator
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path


def observe(operation):
    """将边界异常转为失败事实。@param operation 待执行断言。@return 是否满足。"""
    try:
        return bool(operation())
    except Exception:
        return False


class IndexCount:
    """提供 Python 原生索引协议对照。"""

    def __init__(self, value):
        """保存计数。@param value 整数。@return None。"""
        self.value = value

    def __index__(self):
        """返回真实索引。@return 整数。"""
        return self.value


def array_case(source, count):
    """独立核值、片段与后续编辑。@param source 原始文本。@param count 原生计数。@return 是否一致。"""
    from tomlkit import dumps, parse

    expected = tomllib.loads(source)['a'] * operator.index(count)
    document = parse(source)
    original = document['a']
    result = operator.imul(original, count)
    rendered = dumps(document)
    valid = (result is original is document['a'] and list(original) == expected
        and original.unwrap() == expected and tomllib.loads(rendered)['a'] == expected)
    if operator.index(count) == 1:
        valid = valid and rendered == source
    if operator.index(count) > 0:
        valid = valid and all(comment in rendered for comment in ('# first', '# second') if comment in source)
    valid = valid and '# outside' in rendered and '# tail' in rendered
    original.append(91)
    expected.append(91)
    original[-1] = 92
    expected[-1] = 92
    if expected:
        del original[0]
        del expected[0]
    return valid and original.unwrap() == expected and tomllib.loads(dumps(document))['a'] == expected


def array_alias_case(source, mutation):
    """核重复可变项引用与 Python list 相同。@param source 文本。@param mutation 嵌套操作。@return 是否一致。"""
    from tomlkit import dumps, parse

    expected = tomllib.loads(source)['a'] * 3
    document = parse(source)
    array = document['a']
    array *= 3
    if array[0] is not array[1] or array[0] is not array[2]:
        return False
    mutation(array[0])
    mutation(expected[0])
    return array.unwrap() == expected and tomllib.loads(dumps(document))['a'] == expected


def invalid_counts():
    """无索引协议计数不得先修改数组。@return 是否保留值及字节。"""
    from tomlkit import dumps, parse

    for count in (2.0, '2', None, object()):
        document = parse('a = [1, 2]\n')
        array = document['a']
        before = dumps(document)
        try:
            operator.imul(array, count)
        except TypeError:
            if array.unwrap() != [1, 2] or dumps(document) != before:
                return False
        else:
            return False
    return True


def array_observations():
    """覆盖真实数组重复边界，不读取候选声明。@return 独立断言结果。"""
    sources = ['# outside\na = [1, 2] # tail\n',
        '# outside\na = [\n  1, # first\n  2, # second\n] # tail\n',
        '# outside\na = [] # tail\n',
        '# outside\na = [[1], {x=2}] # tail\n']
    counts = (0, -2, 1, 2, 3, False, True, IndexCount(2))
    return {'repetition_matrix': all(observe(lambda source=source, count=count: array_case(source, count))
            for source in sources for count in counts),
        'invalid_counts_unchanged': observe(invalid_counts),
        'nested_array_alias': observe(lambda: array_alias_case('a = [[1]]\n', lambda item: item.append(7))),
        'inline_value_alias': observe(lambda: array_alias_case('a = [{x=1}]\n', lambda item: item.__setitem__('x', 7)))}


def inline_case(source, paths, expected):
    """按外部预期核叶子删除及后续添加。@param source 文本。@param paths 删除路径。@param expected 独立树。@return 是否一致。"""
    from tomlkit import dumps, parse

    document = parse(source)
    if dumps(document) != source:
        return False
    for path in paths:
        parent = document['t']
        for part in path[:-1]:
            parent = parent[part]
        del parent[path[-1]]
    rendered = dumps(document)
    parsed = tomllib.loads(rendered)
    if document.unwrap() != {'t': expected} or parsed != {'t': expected}:
        return False
    if list(parsed['t']) != list(expected):
        return False
    if any(comment in source and comment not in rendered for comment in ('# before', '# after')):
        return False
    if dumps(parse(rendered)) != rendered:
        return False
    document['t']['b']['new'] = 8
    expected['b']['new'] = 8
    return tomllib.loads(dumps(document)) == {'t': expected}


def flat_deletions():
    """固定普通删除的既有字节，不以自比较掩盖回归。@return 是否保持。"""
    from tomlkit import dumps, parse

    cases = [('t = {a = 1, b = 2, c = 3}', ['c'], 't = {a = 1, b = 2 }'),
        ('t = {a = 1, b = 2, c = 3}', ['b'], 't = {a = 1,  c = 3}'),
        ('t = {a = 1, b = 2}', ['b'], 't = {a = 1 }'),
        ('t = {a = 1, b = 2}', ['a'], 't = { b = 2}'),
        ('t = {a = 1, b = 2, c = 3}', ['b', 'c'], 't = {a = 1  }')]
    for source, keys, expected in cases:
        document = parse(source)
        for key in keys:
            del document['t'][key]
        if dumps(document) != expected:
            return False
    return True


def inline_observations():
    """独立预期保留每个空父表。@return 业务结果。"""
    cases = [
        ('t = {b.c=1, a="", d=1}\n', [('b', 'c')], {'b': {}, 'a': '', 'd': 1}),
        ('t = {a="", b.c=1, d=1}\n', [('b', 'c')], {'a': '', 'b': {}, 'd': 1}),
        ('t = {a="", d=1, b.c=1}\n', [('b', 'c')], {'a': '', 'd': 1, 'b': {}}),
        ('t = {b.c=1}\n', [('b', 'c')], {'b': {}}),
        ('t = {b.c.d=1}\n', [('b', 'c', 'd')], {'b': {'c': {}}}),
        ('t = {"b"."c.d"=1}\n', [('b', 'c.d')], {'b': {}}),
        ('t = {b.c=1, q.r=2, empty={}}\n', [('b', 'c'), ('q', 'r')], {'b': {}, 'q': {}, 'empty': {}}),
        ('t = {b.c=1, b.e=2, x=3}\n', [('b', 'c')], {'b': {'e': 2}, 'x': 3}),
        ('# before\nt = {a=1, b.c=2, d=3} # after\n', [('b', 'c')], {'a': 1, 'b': {}, 'd': 3}),
    ]

    def existing_dotted_insertion():
        """保护已有 dotted 新增规则。@return 是否精确。"""
        from tomlkit import dumps, parse
        document = parse('a = {b.c.e = 1}\n')
        document['a']['b']['c']['g'] = 2
        return dumps(document) == 'a = {b.c.e = 1, b.c.g = 2}\n'

    def explicit_parent_removal():
        """显式删除父键仍应删除。@return 是否符合。"""
        from tomlkit import dumps, parse
        document = parse('t = {b.c=1, x=2}\n')
        del document['t']['b']
        return tomllib.loads(dumps(document)) == {'t': {'x': 2}}

    return {'empty_parent_matrix': all(observe(lambda case=case: inline_case(*case)) for case in cases),
        'flat_delete_bytes': observe(flat_deletions), 'dotted_insertion': observe(existing_dotted_insertion),
        'explicit_parent_removal': observe(explicit_parent_removal)}


def dialect_facts():
    """区分本库 1.1 与消费者 1.0，绝不全量否决 1.1。@return 实际解析事实。"""
    from tomlkit import parse
    source = 'v = "\\e"\n'
    try:
        tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        consumer_rejected = True
    else:
        consumer_rejected = False
    compatible = 'v = "\\u001b"\n'
    return {'escape_value': parse(source)['v'] == '\x1b', 'consumer_rejected': consumer_rejected,
        'compatible_equal': parse(compatible)['v'] == tomllib.loads(compatible)['v'] == '\x1b'}


def facts(mode):
    """生成只读任务的真实事实。@param mode 任务。@return 事实对象。"""
    from tomlkit import dumps, parse
    from tomlkit.toml_file import TOMLFile

    if mode in ('TK-D02', 'TK-P01'):
        return dialect_facts()
    if mode == 'TK-U01':
        source = '# configuration\ndate = 2026-01-02\na = [1, 2] # values\n'
        document = parse(source)
        return {'roundtrip_bytes': dumps(document) == source,
            'date_type': type(document.unwrap()['date']) is date, 'array_value': document.unwrap()['a'] == [1, 2]}
    if mode == 'TK-D03':
        results = []
        for count in (0, 1, 2):
            document = parse('a = [1, 2]\n')
            array = document['a']
            array *= count
            results.append([array.unwrap(), dumps(document), array is document['a']])
        workaround = parse('a = [1, 2]\n')
        workaround['a'].extend(tuple(workaround['a']))
        return {'cases': results, 'workaround': tomllib.loads(dumps(workaround))['a']}
    if mode == 'TK-D04':
        document = parse('t = {a="", b.c=1, d=1}\n')
        del document['t']['b']['c']
        only = parse('t = {b.c=1}\n')
        del only['t']['b']['c']
        return {'middle': dumps(document), 'only': dumps(only), 'retained_parent': only.unwrap() == {'t': {'b': {}}}}
    if mode == 'TK-P02':
        preserved = []
        with tempfile.TemporaryDirectory(prefix='tomlkit-file-facts-') as directory:
            for index, source in enumerate((b'a=1\nb=2\n', b'a=1\r\nb=2\r\n', b'a=1\r\nb=2\n')):
                target = Path(directory) / f'{index}.toml'
                target.write_bytes(source)
                file = TOMLFile(target)
                document = file.read()
                file.write(document)
                preserved.append(target.read_bytes() == source)
        return {'line_endings_preserved': preserved,
            'write_parameters': list(inspect.signature(TOMLFile.write).parameters)}
    raise ValueError(mode)


def consultation(mode, root, answer_path):
    """独立子进程执行回答示例并改变输入。@param mode 任务。@param root 候选。@param answer_path 回答。@return 真实断言。"""
    answer = answer_path.read_text(encoding='utf-8') if answer_path and answer_path.is_file() else ''
    blocks = re.findall(r'```[ \t]*(?:python|py)?[ \t]*\n(.*?)```', answer, re.DOTALL)
    if len(blocks) != 1 or len(blocks[0].encode()) > 65536:
        raise ValueError('示例须为唯一完整有界 Python 代码块')
    ast.parse(blocks[0])
    driver = '''import json,runpy,tomllib
from pathlib import PurePath,PurePosixPath,PureWindowsPath
from tomlkit.items import CUSTOM_ENCODERS
from tomlkit.exceptions import ConvertError
namespace=runpy.run_path('example.py')
mode=MODE
if mode=='TK-C01':
 source="# 配置\\nname = 'old' # owner\\n[server]\\nport = 5432 # port\\nkeep = 'untouched'\\n"
 valid=True
 for name in ('new','中文','a\\\\b',"can't",'line\\nbreak'):
  result=namespace['update_config'](source,name,6432)
  valid=valid and tomllib.loads(result)=={'name':name,'server':{'port':6432,'keep':'untouched'}}
  valid=valid and '# 配置\\n' in result and '# owner' in result and '# port' in result and "keep = 'untouched'\\n" in result
  if name=='new': valid=valid and "name = 'new' # owner" in result
  if "'" in name or '\\n' in name: valid=valid and 'name = "' in result
 count=5
elif mode=='TK-C02':
 source='# plugins\\n[plugins."io.containerd.grpc.v1.cri"]\\nsandbox_image = "old" # target\\n[plugins.other]\\nx=2\\n[plugins.io.containerd]\\nsandbox_image="nested"\\n'
 valid=True
 for image in ('new','镜像 with space','a"b\\\\c'):
  result=namespace['update_plugin'](source,image)
  expected={'plugins':{'io.containerd.grpc.v1.cri':{'sandbox_image':image},'other':{'x':2},'io':{'containerd':{'sandbox_image':'nested'}}}}
  valid=valid and tomllib.loads(result)==expected and '# plugins' in result and '# target' in result and '[plugins.other]\\nx=2\\n' in result
 try: namespace['update_plugin']('[plugins.other]\\nx=2\\n','x')
 except KeyError: pass
 else: valid=False
 count=3
else:
 def sentinel(value): raise ConvertError('unsupported sentinel')
 CUSTOM_ENCODERS.append(sentinel)
 before=tuple(CUSTOM_ENCODERS)
 valid=True
 try:
  for value in (PurePosixPath('build/报告.toml'),PureWindowsPath('build/report.toml')):
   result=namespace['render_artifact'](value)
   valid=valid and tomllib.loads(result)=={'artifact':str(value)} and tuple(CUSTOM_ENCODERS)==before
  try: namespace['render_artifact'](object())
  except ConvertError: pass
  else: valid=False
  valid=valid and tuple(CUSTOM_ENCODERS)==before
 finally: CUSTOM_ENCODERS.remove(sentinel)
 count=3
print(json.dumps({'runnable_example':bool(valid),'varied_input_count':count}))
'''.replace('mode=MODE', 'mode=' + repr(mode))
    with tempfile.TemporaryDirectory(prefix='tomlkit-example-') as directory:
        work = Path(directory)
        (work / 'example.py').write_text(blocks[0], encoding='utf-8')
        (work / 'driver.py').write_text(driver, encoding='utf-8')
        environment = dict(os.environ, PYTHONPATH=str(root / 'library'), PYTHONDONTWRITEBYTECODE='1')
        completed = subprocess.run([sys.executable, '-B', str(work / 'driver.py')], cwd=work,
            env=environment, capture_output=True, timeout=8, check=False)
        if completed.returncode or len(completed.stdout) > 65536 or len(completed.stderr) > 65536:
            raise ValueError('回答示例运行失败：' + completed.stderr[-1500:].decode(errors='replace'))
        return json.loads(completed.stdout)


def main():
    """执行一个固定模式并输出独立 JSON。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode')
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    parser.add_argument('--answer-file', type=Path, default=Path(os.environ['PROJECT_ANSWER_FILE']) if os.environ.get('PROJECT_ANSWER_FILE') else None)
    args = parser.parse_args()
    root = args.candidate_root.resolve()
    sys.path.insert(0, str(root / 'library'))
    import tomlkit
    imported = Path(tomlkit.__file__).resolve().is_relative_to(root / 'library')
    if args.mode == 'TK-M01':
        result = array_observations()
    elif args.mode == 'TK-M02':
        result = inline_observations()
    elif args.mode in ('TK-C01', 'TK-C02', 'TK-C03'):
        result = consultation(args.mode, root, args.answer_file)
    else:
        result = facts(args.mode)
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
