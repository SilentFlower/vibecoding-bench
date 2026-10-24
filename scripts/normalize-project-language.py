#!/usr/bin/env python3
"""规范化 Claude 可见的工程说明语言，保留中文页面字段和原始业务字面。"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import read_document, safe_relative


HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]')
RUBRIC_TRANSLATIONS = {
    '调查真实源码、说明调用路径并澄清业务，获得方案确认后实施；交付真实工程改动、原版失败的公开回归和中文兼容说明；独立失败返工，不以问答或文档单独计数。':
        'Investigate the real source, explain the call path and clarify the business requirements before obtaining plan approval and implementing. Deliver real engineering changes, public regression tests that fail on the original version, and English compatibility documentation. Repair independently reported failures; questions, answers and documentation do not count as separate completed objectives.',
    '必须交付授权源码、能在原版失败的公开回归和中文兼容说明；所有冻结原生回归通过。':
        'Deliver the authorized source changes, public regression tests that fail on the original version, and English compatibility documentation. All frozen native regression tests must pass.',
    '按实际业务和冻结边界接受等价实现，不按参考补丁文本评分。':
        'Accept equivalent implementations according to actual business behavior and the frozen scope; do not grade by matching the reference patch text.',
    '依据真实程序行为接受等价实现，不按参考文本或篇幅评分。':
        'Accept equivalent implementations according to actual program behavior; do not grade by matching reference text or its length.',
}


def docstring_spans(source: str) -> list[tuple[int, int, str, str]]:
    """定位真正的 Python 文档串，不将测试数据或任意字符串当成说明。

    :param source: 待检查的 Python 源码。
    :return: 字符偏移起止、所属节点类型和节点名称。
    """
    lines = source.splitlines(keepends=True)
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line)

    def position(line: int, byte_column: int) -> int:
        """将 AST 的 UTF-8 字节列转换为字符串字符偏移。:param line: 行号。:param byte_column: 字节列。:return: 字符偏移。"""
        return offsets[line - 1] + len(lines[line - 1].encode()[:byte_column].decode())

    result = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            result.append((position(first.lineno, first.col_offset), position(first.end_lineno, first.end_col_offset),
                type(node).__name__, getattr(node, 'name', 'module')))
    return result


def python_evidence(source: str) -> tuple[str, list[str]]:
    """同时冻结可执行 AST 和文档串之外的原始字符串 token。

    :param source: 可解析的 Python 文本。
    :return: 去除文档串的 AST 和业务字符串原始 token 列表。
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                del node.body[0]
    spans = docstring_spans(source)
    lines = source.splitlines(keepends=True)
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line)
    strings = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING:
            continue
        start = offsets[token.start[0] - 1] + token.start[1]
        end = offsets[token.end[0] - 1] + token.end[1]
        if not any(left <= start and end <= right for left, right, _, _ in spans):
            strings.append(token.string)
    return ast.dump(tree, include_attributes=False), strings


def normalize_python(source: str, task_id: str, contract: str) -> tuple[str, int]:
    """将生成测试的中文文档串改成简短英文角色说明，保留全部执行语义。

    :param source: 公开测试源码。
    :param task_id: 当前工程目标标识。
    :param contract: 对应完整英文合同的工作区相对路径。
    :return: 新源码及实际替换的文档串数量。
    """
    changes = []
    for left, right, kind, name in docstring_spans(source):
        if not HAN.search(source[left:right]):
            continue
        if kind == 'Module':
            description = f'Public regression tests for {task_id}; the complete business contract is in {contract}.'
        elif kind == 'ClassDef':
            description = f'Public regression fixture: {name}.'
        elif name.startswith('test_'):
            description = 'Verify ' + name.removeprefix('test_').replace('_', ' ') + '.'
        else:
            description = f'Support the public regression through {name}.'
        changes.append((left, right, json.dumps(description, ensure_ascii=True)))
    revised = source
    for left, right, replacement in sorted(changes, reverse=True):
        revised = revised[:left] + replacement + revised[right:]
    # AST 相同仍不足以证明原始业务字面没有被重写，因此额外比较每个非文档串 token 的原字节表达。
    if python_evidence(source) != python_evidence(revised):
        raise ValueError('说明规范化改变了可执行测试或业务字面：' + task_id)
    return revised, len(changes)


def normalize(root: Path, *, apply: bool = False, translations: Path | None = None,
              version: str = 'real-development-cycles-v3-600-en-20261024') -> dict:
    """按当前目录规范化生成材料及评审说明，默认仅预览。

    :param root: 项目内容库根目录。
    :param apply: 是否将已经完整校验的候选文本写回工作树。
    :param translations: 旧材料的逐文件精确翻译映射，可为空。
    :param version: 新内容目录版本，不修改已经安装的历史 release。
    :return: 目标数量、变更摘要及 AST 等价证明。
    """
    root = root.resolve()
    if root.parent.name == 'releases' and re.fullmatch(r'[a-f0-9]{64}', root.name):
        raise ValueError('已安装的历史内容版本不可原地规范化，请在可编辑内容库生成新版本')
    catalog = read_document(root / 'catalog.json')
    planned, declared, tests = {}, set(), []
    objectives = generated = docstrings = prompts = rubrics = 0

    def plan(path: Path, text: str) -> None:
        """累计候选内容，冲突时停止而不覆盖。:param path: 库内路径。:param text: 新文本。:return: None。"""
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('规范化路径不属于普通内容文件')
        if path in planned and planned[path] != text:
            raise ValueError('同一文件收到不同的规范化内容：' + str(path))
        if path.read_text() != text:
            planned[path] = text

    def encode(value: object) -> str:
        """使用项目既有格式序列化 JSON。:param value: JSON 数据。:return: 缩进文本。"""
        return json.dumps(value, ensure_ascii=False, indent=2) + '\n'

    for key in catalog['projects']:
        project = root / 'projects' / safe_relative(key)
        manifest_path = project / safe_relative(catalog['project_manifest'])
        manifest = read_document(manifest_path)
        for scene in manifest['scenarios']:
            for task in scene['tasks']:
                if task.get('development_cycle') not in ('feature', 'bug'):
                    continue
                objectives += 1
                sources = [*task['materials'], *task.get('owner_materials', [])]
                sources += [item['source'] for item in task.get('setup', [])]
                declared.update(project / safe_relative(source) for source in sources)
                previous_prompt = task['prompt']
                task['prompt'] = previous_prompt.replace('Chinese compatibility documentation', 'English compatibility documentation')
                prompts += task['prompt'] != previous_prompt
                contract = f'materials/{task["id"]}-contract.md'
                if contract not in task['materials']:
                    continue
                generated += 1
                # 英文 prompt 已含完整接口、边界及授权路径；页面中文简述不能替代正式合同。
                authorization = '\n'.join('- ' + path for path in task['allowed_paths'])
                scope = task['prompt'] + '\n\nAuthorized paths:\n' + authorization
                plan(project / contract, '# Engineering contract: ' + task['id'] + '\n\n' + scope + '\n')
                business = f'disclosure/{task["id"]}-business.md'
                if business not in task.get('owner_materials', []):
                    raise ValueError('标准目标缺少对应公开业务确认：' + task['id'])
                plan(project / business, '# Business scope and confirmation\n\n' + scope +
                    '\n\nPublic examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.\n')
                for relative in task['materials']:
                    if not relative.endswith('.py'):
                        continue
                    path = project / safe_relative(relative)
                    before = path.read_text()
                    revised, count = normalize_python(before, task['id'], contract)
                    docstrings += count
                    plan(path, revised)
                    tests.append({'path':str(path.relative_to(root)), 'executable_ast_unchanged':True,
                        'business_string_tokens_unchanged':True, 'translated_docstrings':count})
                rubric_path = project / safe_relative(task['evaluation']['rubric'])
                rubric = read_document(rubric_path)
                changed = False
                for criterion in rubric['criteria']:
                    previous = criterion['requirement']
                    criterion['requirement'] = RUBRIC_TRANSLATIONS.get(previous, previous)
                    if criterion['id'] != 'business' and HAN.search(criterion['requirement']):
                        raise ValueError('尚未准确翻译的评审流程说明：' + task['id'])
                    changed |= previous != criterion['requirement']
                previous = rubric['comparison']
                rubric['comparison'] = RUBRIC_TRANSLATIONS.get(previous, previous)
                if HAN.search(rubric['comparison']):
                    raise ValueError('尚未准确翻译的评审比较说明：' + task['id'])
                changed |= previous != rubric['comparison']
                if changed:
                    if task['evaluation']['version'] != rubric['version']:
                        raise ValueError('工程合同与评审版本不一致：' + task['id'])
                    rubric['version'] += 1
                    task['evaluation']['version'] = rubric['version']
                    rubrics += 1
                plan(rubric_path, encode(rubric))
        plan(manifest_path, encode(manifest))

    if translations and translations.is_file():
        mapping = read_document(translations)
        if mapping.get('schema') != 1 or not isinstance(mapping.get('files'), dict):
            raise ValueError('旧材料翻译映射格式不正确')
        for relative, replacements in mapping['files'].items():
            relative = relative.removeprefix('project_library/')
            path = root / safe_relative(relative)
            if path not in declared or path in planned or not isinstance(replacements, dict):
                raise ValueError('翻译映射必须仅属于未生成的公开输入：' + relative)
            before = path.read_text()
            revised = before
            for previous, replacement in replacements.items():
                if not previous or not isinstance(replacement, str):
                    raise ValueError('翻译映射包含非法文本')
                if previous in revised:
                    revised = revised.replace(previous, replacement)
                elif replacement not in revised:
                    raise ValueError('待翻译材料已变化：' + relative)
            if path.suffix == '.py' and python_evidence(before) != python_evidence(revised):
                raise ValueError('旧材料翻译改变了可执行逻辑或业务字面：' + relative)
            plan(path, revised)

    for name in ('catalog.json', 'catalog-development.json'):
        path = root / name
        if path.is_file():
            document = read_document(path)
            document['version'] = version
            plan(path, encode(document))
    changes = [{'path':str(path.relative_to(root)),
        'before_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'after_sha256':hashlib.sha256(text.encode()).hexdigest()} for path, text in sorted(planned.items())]
    if apply:
        for path, text in planned.items():
            path.write_text(text)
    return {'status':'applied' if apply else 'changes_pending' if changes else 'passed',
        'projects':len(catalog['projects']), 'objectives':objectives, 'generated_objectives':generated,
        'prompts_updated':prompts, 'rubrics_updated':rubrics, 'docstrings_updated':docstrings,
        'changed_files':changes, 'python_equivalence':tests, 'historical_releases_modified':False}


def main() -> None:
    """解析预览、应用和检查选项，不运行模型或外部服务。:return: None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'project_library')
    parser.add_argument('--translations', type=Path, default=ROOT / 'scripts/project-material-language-translations.json')
    parser.add_argument('--version', default='real-development-cycles-v3-600-en-20261024')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = normalize(args.root, apply=args.apply, translations=args.translations, version=args.version)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('changed_files','python_equivalence')}
        | {'changed_file_count':len(result['changed_files'])}, ensure_ascii=False))
    if args.check and result['changed_files']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
