"""隔离观察 Jinja 候选的业务行为；固定 JSON 由控制端比较。"""
from __future__ import annotations

import argparse
import ast
import asyncio
from collections import UserDict
from collections.abc import Mapping
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl


def observe(operation):
    """记录单项观察，异常不能冒充通过。@param operation 业务调用。@return 观察或异常类型。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


class ReadOnlyMapping(Mapping):
    """提供真实只读 Mapping 对照，避免只针对 UserDict 特判。"""

    def __init__(self, pairs):
        """冻结输入项。@param pairs 键值序列。@return None。"""
        self.data = dict(pairs)

    def __getitem__(self, key):
        """读取键。@param key 键。@return 对应值。"""
        return self.data[key]

    def __iter__(self):
        """保持原始插入顺序。@return 键迭代器。"""
        return iter(self.data)

    def __len__(self):
        """返回项数。@return 长度。"""
        return len(self.data)


def mapping_observations():
    """验证 Mapping 修复及原输入兼容。@return 独立真实观察。"""
    from jinja2.filters import do_urlencode

    pairs = [('q', 'A+1 & /'), ('Aa', ''), ('中文', '值+空 格'), ('', 'empty')]

    def encoded(factory):
        """用标准库独立解码结果。@param factory Mapping构造器。@return 是否严格保持items。"""
        return parse_qsl(do_urlencode(factory(pairs)), keep_blank_values=True) == pairs

    def bad_pair():
        """保留原版非法 pair 错误传播。@return 是否抛出 ValueError。"""
        try:
            do_urlencode([('one',)])
        except ValueError:
            return True
        return False

    return {'dict_items': observe(lambda: encoded(dict)),
        'userdict_items': observe(lambda: encoded(UserDict)),
        'readonly_mapping_items': observe(lambda: encoded(ReadOnlyMapping)),
        'duplicate_pairs': observe(lambda: parse_qsl(do_urlencode([('q', 'a'), ('q', 'b')])) == [('q', 'a'), ('q', 'b')]),
        'string_path': observe(lambda: do_urlencode('a/b c+中') == 'a/b%20c%2B%E4%B8%AD'),
        'invalid_pairs_raise': observe(bad_pair)}


def map_observations():
    """检查显式缺省值、异步、嵌套及共享调用方。@return 独立观察。"""
    from jinja2 import Environment, StrictUndefined, Undefined

    rows = [{}, {'field': None}, {'field': False}, {'field': 0}, {'field': ''}]

    def sync_result(default, *, omitted=False, strict=False, attribute='field', data=None):
        """执行同步实际过滤器。@param default 默认值。@return 实际值列表。"""
        env = Environment(undefined=StrictUndefined if strict else Undefined)
        expression = 'rows|map(attribute=attribute' + ('' if omitted else ', default=fallback') + ')|list'
        return env.compile_expression(expression, undefined_to_none=False)(rows=rows if data is None else data, attribute=attribute, fallback=default)

    async def async_result(default, omitted=False):
        """经真实异步模板捕获类型。@param default 默认值。@param omitted 是否省略。@return 值列表。"""
        captured = []
        env = Environment(enable_async=True)
        env.filters['record_values'] = lambda values: captured.extend(values) or ''
        source = '{{ rows|map(attribute="field"' + ('' if omitted else ', default=fallback') + ')|list|record_values }}'
        await env.from_string(source).render_async(rows=rows, fallback=default)
        return captured

    def types_preserved(values, missing):
        """严格检查类型，避免False与0相等掩盖错误。@param values 实际值。@param missing 首项。@return 是否精确。"""
        expected = [missing, None, False, 0, '']
        return len(values) == 5 and all(type(a) is type(b) and a == b for a, b in zip(values, expected))

    def shared_callers():
        """共享getter的既有调用仍正常。@return 是否保持。"""
        env = Environment()
        data = [{'k':'b', 'v':2}, {'k':'a', 'v':1}, {'k':'b', 'v':3}]
        return (env.compile_expression("rows|sum(attribute='v')")(rows=data) == 6
            and env.compile_expression("rows|unique(attribute='k')|list")(rows=data) == data[:2]
            and [(item.grouper, len(item.list)) for item in env.compile_expression("rows|groupby('k')")(rows=data)] == [('a',1),('b',2)])

    return {'explicit_none_sync': observe(lambda: types_preserved(sync_result(None), None)),
        'omitted_sync_undefined': observe(lambda: isinstance(sync_result(None, omitted=True)[0], Undefined)),
        'false_default': observe(lambda: types_preserved(sync_result(False), False)),
        'zero_default': observe(lambda: types_preserved(sync_result(0), 0)),
        'empty_default': observe(lambda: types_preserved(sync_result(''), '')),
        'explicit_none_async': observe(lambda: types_preserved(asyncio.run(async_result(None)), None)),
        'omitted_async_undefined': observe(lambda: isinstance(asyncio.run(async_result(None, True))[0], Undefined)),
        'strict_explicit_none': observe(lambda: types_preserved(sync_result(None, strict=True), None)),
        'strict_omitted_undefined': observe(lambda: isinstance(sync_result(None, omitted=True, strict=True)[0], StrictUndefined)),
        'nested_missing': observe(lambda: sync_result(None, attribute='account.name', data=[{}, {'account': {}}, {'account': {'name':'研发'}}]) == [None,None,'研发']),
        'shared_callers': observe(shared_callers),
        **{'preserved_mapping_' + key: value for key,value in mapping_observations().items()}}


def extract_program(answer):
    """复用明确单代码块规则，拒绝歧义。@param answer 冻结回答。@return 唯一程序。"""
    blocks = re.findall(r'```[ \t]*(?:python|py)?[ \t]*\n(.*?)```', answer, re.DOTALL)
    if len(blocks) != 1 or len(blocks[0].encode('utf-8')) > 65536:
        raise ValueError('需要一个有界完整Python代码块')
    ast.parse(blocks[0])
    return blocks[0]


def run_program(code, root, payload, mode):
    """在独立业务目录执行答案并观察输出和文件。@param code 程序。@param root 候选。@param payload 变化输入。@param mode 业务模式。@return 实际结果。"""
    with tempfile.TemporaryDirectory(prefix='jinja-example-') as directory:
        business = Path(directory)
        (business/'input.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        (business/'example.py').write_text(code, encoding='utf-8')
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join([str(root/'library/src'), *[p for p in sys.path if p and 'dependencies' in p]])
        stdout, stderr = business/'stdout.txt', business/'stderr.txt'
        with stdout.open('wb') as out, stderr.open('wb') as err:
            completed = subprocess.run([sys.executable, '-B', str(business/'example.py')], cwd=business, env=env, stdout=out, stderr=err, timeout=8, check=False)
        if completed.returncode or stdout.stat().st_size > 65536 or stderr.stat().st_size > 65536:
            return {'program_error': True}
        result = json.loads(stdout.read_text(encoding='utf-8'))
        if mode == 'JI-C03':
            expected = payload['text'].encode('utf-8')
            files = [business/name for name in ('report.html','text-stream.txt','binary-stream.bin')]
            return {'output':result,'file_bytes_match':all(p.is_file() and not p.is_symlink() and p.read_bytes()==expected for p in files)}
        return result


def consultation(mode, root, answer_file):
    """运行示例及变化输入，固定事实不代替答复质量。@param mode 任务。@param root 候选。@param answer_file 回答。@return 检查结果。"""
    from html import escape
    answer = answer_file.read_text(encoding='utf-8') if answer_file and answer_file.is_file() and answer_file.stat().st_size <= 262144 else ''
    code = extract_program(answer)
    if mode == 'JI-C01':
        inputs = [{'title':'<评审>'},{'title':'<复核 & "确认">'}]
        outputs = [run_program(code,root,payload,mode) for payload in inputs]
        # MarkupSafe采用&#34;，标准库escape采用&quot;，这里允许同等HTML实体。
        from html import unescape
        valid = all(isinstance(out,dict) and set(out)=={'html','text','upper_html','string'} and out['text']==payload['title']
            and all(isinstance(out[key],str) and unescape(out[key])==payload['title'] and '<' not in out[key] for key in ('html','upper_html','string')) for payload,out in zip(inputs,outputs))
    elif mode == 'JI-C02':
        inputs = [{'rows':[{'x':'d'},{'x':'a'}]},{'rows':[{'x':'中'},{'x':'a'},{'x':'a'}]},{'rows':[]}]
        valid = all(run_program(code,root,payload,mode)==sorted(row['x'] for row in payload['rows']) for payload in inputs)
    else:
        inputs = [{'text':'中文'},{'text':'第二份 & <内容>\n'}]
        outputs = [run_program(code,root,payload,mode) for payload in inputs]
        valid = all(out=={'output':{'text_stream_open':True,'binary_stream_open':True},'file_bytes_match':True} for out in outputs)
    return {'runnable_example':valid,'varied_input_count':len(inputs)}


def facts(mode):
    """观察非修改任务的冻结事实。@param mode 任务。@return 独立事实。"""
    from jinja2 import ChoiceLoader, DictLoader, Environment, TemplateNotFound, TemplateSyntaxError
    from jinja2 import meta
    from jinja2.filters import do_urlencode

    if mode == 'JI-U01':
        env=Environment(loader=DictLoader({'base.html':'<h1>{{ title }}</h1>{% block body %}{% endblock %}', 'weekly.html':"{% extends 'base.html' %}{% block body %}{% for metric in metrics %}<p>{{ metric }}</p>{% endfor %}{% endblock %}"}))
        template=env.get_template('weekly.html')
        return {'rendered':template.render(title='研发周报',metrics=['完成3项','修复2项','待办1项']), 'changed_context':template.render(title='研发周报',metrics=['变更1项'])}
    if mode == 'JI-P01':
        env=Environment(loader=ChoiceLoader([DictLoader({'weekly.html':'CUSTOM','bad.html':'{% broken %}'}),DictLoader({'weekly.html':'SHARED','base.html':'BASE','bad.html':'GOOD'})]))
        def raises(name,error):
            """确认错误仍传播。@param name 模板。@param error 类型。@return 是否正确。"""
            try:env.get_template(name)
            except error:return True
            return False
        return {'override':env.get_template('weekly.html').render(),'fallback':env.get_template('base.html').render(),'missing_raises':raises('missing.html',TemplateNotFound),'syntax_propagates':raises('bad.html',TemplateSyntaxError)}
    if mode == 'JI-D02':
        loader=DictLoader({'weekly.txt':'v1'});env=Environment(loader=loader,auto_reload=False);old=env.get_template('weekly.txt');first=old.render();loader.mapping['weekly.txt']='v2';cached=env.get_template('weekly.txt').render();env.cache.clear();fresh=env.get_template('weekly.txt').render()
        loader2=DictLoader({'x':'v1'});reload=Environment(loader=loader2,auto_reload=True);before=reload.get_template('x').render();loader2.mapping['x']='v2';after=reload.get_template('x').render()
        return {'cached':[first,cached],'after_clear':fresh,'old_template':old.render(),'auto_reload':[before,after]}
    if mode == 'JI-D03':
        default=Environment();keep=Environment(keep_trailing_newline=True)
        return {'default_render':default.from_string('x\n').render(),'default_stream':''.join(default.from_string('x\n').stream()),'keep_render':keep.from_string('x\n').render(),'keep_stream':''.join(keep.from_string('x\n').stream()),'variable_newline':default.from_string('{{ value }}').render(value='x\n'),'no_source_newline':keep.from_string('x').render()}
    if mode == 'JI-D04':
        # 此任务无代码依赖，固定场景原版才是其运行输入。
        return {'dict':do_urlencode({'Aa':'A+1'}),'userdict':observe(lambda:do_urlencode(UserDict({'Aa':'A+1'}))),'single_key':observe(lambda:do_urlencode(UserDict({'q':'A+1'}))),'workaround':do_urlencode(UserDict({'Aa':'A+1'}).items()),'duplicates':do_urlencode([('q','a'),('q','b')]),'path':do_urlencode('a/b c')}
    if mode == 'JI-P02':
        page="{% extends 'base.html' %}{% block body %}{% include section %}{% endblock %}"
        env=Environment(loader=DictLoader({'page.html':page,'base.html':'<main>{% block body %}{% endblock %}</main>','a.html':'A','b.html':'B'}))
        return {'static_references':list(meta.find_referenced_templates(env.parse(page))),'render_a':env.get_template('page.html').render(section='a.html'),'render_b':env.get_template('page.html').render(section='b.html')}
    raise ValueError(mode)


def main():
    """执行一个显式任务模式。@return None。"""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode')
    parser.add_argument('--candidate-root',type=Path,default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT','/work/project')))
    parser.add_argument('--answer-file',type=Path,default=Path(os.environ['PROJECT_ANSWER_FILE']) if os.environ.get('PROJECT_ANSWER_FILE') else None)
    args=parser.parse_args();root=args.candidate_root.resolve()
    sys.path.insert(0,str(root/'library/src'))
    import jinja2
    from jinja2 import filters
    imported=Path(jinja2.__file__).resolve().is_relative_to(root/'library/src') and Path(filters.__file__).resolve().is_relative_to(root/'library/src')
    if args.mode=='JI-M01':result=mapping_observations()
    elif args.mode=='JI-M02':result=map_observations()
    elif args.mode in ('JI-C01','JI-C02','JI-C03'):result=consultation(args.mode,root,args.answer_file)
    else:result=facts(args.mode)
    print(json.dumps({'candidate_import':imported,**result},ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    main()
