"""独立观察冻结候选的文档业务行为，由控制端比较固定 JSON。

本脚本只在隔离验证容器或显式校准目录执行，不修改持续候选工作区。
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Callable


WEEKLY = '---\ntitle: 资料整理周报\nauthor: 小林\ntags:\n  - 文档\n  - 图片\n---\n\n本周完成归档，下一步核对目录。\n'
VARIANT = '---\ntitle: 归档复核\nauthor: 小周\ntags:\n  - 清单\n  - 备份\n---\n\n保留这一段业务正文。\n'


def observe_case(operation: Callable[[], bool]) -> object:
    """封存单项真实观察，异常不能冒充通过。@param operation 业务调用。@return 布尔或异常类型。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


def repair_observations(module: ModuleType) -> dict:
    """验证保留键修复及公开兼容边界。@param module 实际候选模块。@return 独立用例观察。"""
    from frontmatter.default_handlers import YAMLHandler

    text = '---\ncontent: 备用摘要\nhandler: 业务格式标签\ntitle: 资料\n---\n正文'

    def content_field() -> bool:
        """核对业务摘要与正文分离。@return 是否符合读取合同。"""
        post = module.loads('---\ncontent: 备用摘要\n---\n正文')
        return post['content'] == '备用摘要' and post.content == '正文'

    def handler_field() -> bool:
        """核对业务 handler 不替代实际处理器。@return 是否正确。"""
        post = module.loads('---\nhandler: 业务格式标签\n---\n正文')
        return post['handler'] == '业务格式标签' and isinstance(post.handler, YAMLHandler)

    def roundtrip() -> bool:
        """用两个保留字段和普通字段验证往返。@return 是否全部保留。"""
        first = module.loads(text)
        second = module.loads(module.dumps(first))
        return second.metadata == {'content': '备用摘要', 'handler': '业务格式标签', 'title': '资料'} and second.content == '正文'

    def explicit_handler() -> bool:
        """核对显式处理器对象身份。@return 是否保留同一对象。"""
        handler = YAMLHandler()
        post = module.loads(text, handler=handler)
        return post.handler is handler and post['handler'] == '业务格式标签'

    def old_constructors() -> bool:
        """保持已有 Post 调用形式。@return 两种形式是否有效。"""
        handler = YAMLHandler()
        first = module.Post('正文', title='资料')
        second = module.Post('正文', handler=handler, title='资料')
        return first.content == '正文' and first['title'] == '资料' and second.handler is handler

    def empty_metadata() -> bool:
        """保持空头部及无头部行为。@return 是否正常读取。"""
        with_header = module.loads('---\n---\n正文')
        without_header = module.loads('正文')
        return with_header.metadata == without_header.metadata == {} and with_header.content == without_header.content == '正文'

    def null_content() -> bool:
        """保留 null 业务摘要。@return 空值与正文是否分离。"""
        post = module.loads('---\ncontent: null\n---\n正文')
        return post['content'] is None and post.content == '正文'

    def defaults_only() -> bool:
        """验证从 defaults 来的 content 也不冲突。@return 是否保留。"""
        post = module.loads('正文', content='默认摘要')
        return post['content'] == '默认摘要' and post.content == '正文'

    def document_overrides() -> bool:
        """保留文档元数据优先于同名默认值。@return 是否正确覆盖。"""
        post = module.loads('---\ncontent: 文档摘要\n---\n正文', content='默认摘要')
        return post['content'] == '文档摘要' and post.content == '正文'

    def load_variants() -> bool:
        """经过真实路径和文本流调用统一读取入口。@return 两条路径是否一致。"""
        with tempfile.TemporaryDirectory(prefix='fm-load-') as directory:
            path = Path(directory) / 'document.md'
            path.write_text(text, encoding='utf-8')
            by_path = module.load(path)
            by_stream = module.load(io.StringIO(text))
            return by_path.metadata == by_stream.metadata and by_path.content == by_stream.content == '正文'

    def to_dict_unchanged() -> bool:
        """保持既有扁平导出中正文覆盖同名键的合同。@return 是否没有顺带改 API。"""
        post = module.Post('正文', title='资料')
        post.metadata['content'] = '业务摘要'
        return post.to_dict() == {'title': '资料', 'content': '正文'} and post['content'] == '业务摘要'

    operations = {'content_field': content_field, 'handler_field': handler_field,
        'combined_fields_roundtrip': roundtrip, 'explicit_handler_identity': explicit_handler,
        'old_constructors': old_constructors, 'empty_metadata': empty_metadata,
        'null_content_metadata': null_content, 'defaults_only': defaults_only,
        'document_overrides_default': document_overrides, 'load_path_and_stream': load_variants,
        'to_dict_unchanged': to_dict_unchanged}
    return {name: observe_case(operation) for name, operation in operations.items()}


def runnable_programs(answer: str, root: Path) -> list[str]:
    """枚举有界代码候选，不把第一块自动当答案。

    @param answer 冻结回答。@param root 候选根。@return 去重后可编译的代码候选。
    """
    blocks = re.findall(r'```[ \t]*(?:python|py)?[ \t]*\n(.*?)```', answer, flags=re.DOTALL)
    if not blocks and answer.strip():
        blocks = [answer]
    written = root / 'app/example.py'
    if written.is_file() and not written.is_symlink() and written.stat().st_size <= 65536:
        blocks.append(written.read_text(encoding='utf-8'))
    if len(blocks) > 8:
        raise ValueError('可执行片段超过冻结枚举上限')
    result = []
    for block in blocks:
        code = block.strip() + '\n'
        if len(code.encode('utf-8')) > 65536 or code in result:
            continue
        try:
            ast.parse(code, filename='example.py')
        except SyntaxError:
            continue
        result.append(code)
    return result


def run_program(code: str, root: Path, module: ModuleType, source_text: str) -> dict:
    """在全新业务目录运行一个候选用法并独立读回文件。

    @param code 候选代码。@param root 候选根。@param module 可信加载位置核对后的模块。
    @param source_text 固定业务输入。@return 实际观察或有界失败。
    """
    with tempfile.TemporaryDirectory(prefix='fm-consult-') as directory:
        business = Path(directory)
        original = source_text.encode('utf-8')
        (business / 'weekly.md').write_bytes(original)
        (business / 'example.py').write_text(code, encoding='utf-8')
        environment = dict(os.environ)
        environment['PYTHONPATH'] = os.pathsep.join([str(root / 'library'), str(root / 'app')])
        stdout_path, stderr_path = business / 'stdout.txt', business / 'stderr.txt'
        try:
            with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
                completed = subprocess.run([sys.executable, str(business / 'example.py')], cwd=business,
                    env=environment, stdout=stdout, stderr=stderr, timeout=8, check=False)
        except subprocess.TimeoutExpired:
            return {'error': 'example_timeout'}
        if stdout_path.stat().st_size > 1048576 or stderr_path.stat().st_size > 1048576:
            return {'error': 'example_output_too_large'}
        if completed.returncode != 0:
            return {'returncode': completed.returncode}
        target = business / 'weekly-reviewed.md'
        if not target.is_file() or target.is_symlink() or target.stat().st_size > 65536:
            return {'error': 'output_missing_or_invalid'}
        result = module.load(target)
        initial = module.loads(source_text)
        stdout = stdout_path.read_text(encoding='utf-8', errors='replace')
        return {'returncode': completed.returncode, 'input_unchanged': (business / 'weekly.md').read_bytes() == original,
            'title_printed': initial['title'] in stdout,
            'tags_printed': all(tag in stdout for tag in initial['tags']),
            'metadata': result.metadata, 'body': result.content}


def consult_observations(module: ModuleType, root: Path, answer_file: Path | None) -> dict:
    """挑选唯一满足独立往返的完整程序，拒绝歧义。

    @param module 候选库。@param root 候选根。@param answer_file 控制端冻结回答。@return 实际往返。
    """
    answer = ''
    if answer_file is not None and answer_file.is_file():
        if answer_file.stat().st_size > 262144:
            return {'error': 'answer_too_large'}
        answer = answer_file.read_text(encoding='utf-8')
    programs = runnable_programs(answer, root)
    passing = []
    for code in programs:
        observed = run_program(code, root, module, WEEKLY)
        expected_metadata = {'title': '资料整理周报', 'author': '小林', 'tags': ['文档', '图片'], 'status': '已校对'}
        if (observed.get('returncode') == 0 and observed.get('input_unchanged') is True
                and observed.get('metadata') == expected_metadata
                and observed.get('body') == '本周完成归档，下一步核对目录。'
                and observed.get('title_printed') is True and observed.get('tags_printed') is True):
            variant = run_program(code, root, module, VARIANT)
            variant_ok = (variant.get('returncode') == 0 and variant.get('input_unchanged') is True
                and variant.get('metadata') == {'title': '归档复核', 'author': '小周', 'tags': ['清单', '备份'], 'status': '已校对'}
                and variant.get('body') == '保留这一段业务正文。'
                and variant.get('title_printed') is True and variant.get('tags_printed') is True)
            observed['variant_preserved'] = variant_ok
            if variant_ok:
                passing.append(observed)
    if len(passing) != 1:
        return {'unique_program': False, 'passing_program_count': len(passing), 'program_count': len(programs)}
    return {'unique_program': True, **passing[0]}


def main() -> None:
    """执行显式观察模式并输出单一 JSON。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['consult', 'shallow', 'repair'])
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    parser.add_argument('--answer-file', type=Path, default=Path(os.environ['PROJECT_ANSWER_FILE']) if os.environ.get('PROJECT_ANSWER_FILE') else None)
    options = parser.parse_args()
    root = options.candidate_root.resolve()
    sys.path.insert(0, str(root / 'app'))
    sys.path.insert(0, str(root / 'library'))
    import frontmatter

    loaded_path = Path(frontmatter.__file__).resolve()
    imported = loaded_path.is_relative_to((root / 'library').resolve())
    if options.mode == 'repair':
        result = repair_observations(frontmatter)
    elif options.mode == 'shallow':
        defaults = {'theme': 'light', 'lang': 'zh'}
        metadata, body = frontmatter.parse('---\nsettings:\n  theme: dark\n---\n正文', settings=defaults)
        result = {'metadata': metadata, 'body': body, 'defaults': defaults}
    else:
        result = consult_observations(frontmatter, root, options.answer_file)
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
