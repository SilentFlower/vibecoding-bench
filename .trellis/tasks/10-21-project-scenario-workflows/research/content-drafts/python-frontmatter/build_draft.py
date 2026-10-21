"""在本研究目录生成 python-frontmatter 场景草案，不改正式内容或上游。

执行本脚本只复制已有固定源码和生成静态素材，不运行候选、原生测试或模型。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
DRAFT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = REPOSITORY_ROOT / '.deploy/github-100-research/resume-app/python-frontmatter/source'
COMMIT = 'd2977d71638cb451bc06f2af3bb48e09e0dbe8c6'
sys.path.insert(0, str(REPOSITORY_ROOT / 'orchestrator'))
from project_library import snapshot_tree


def write_text(relative: str, value: str) -> None:
    """写入研究根内 UTF-8 文件。@param relative 相对路径。@param value 内容。@return None。"""
    path = DRAFT_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8')


def write_json(relative: str, value: object) -> None:
    """保存可审阅 JSON。@param relative 相对路径。@param value 数据。@return None。"""
    write_text(relative, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def criterion(key: str, requirement: str, evidence: list[str] | None = None) -> dict:
    """构造当前真实格式的评审项。@param key 标识。@param requirement 要求。@param evidence 证据。@return 判据。"""
    return {'id': key, 'requirement': requirement, 'evidence': evidence or []}


def task(key: str, kind: str, goal: str, prompt: str, *, materials: list[str] | None = None,
         allowed: list[str] | None = None, native: str | None = None,
         outcomes: list[str] | None = None, branches: list[dict] | None = None) -> dict:
    """构造稳定任务。@param key 标识。@param kind 类型。@param goal 目标。@param prompt 首问。

    @param materials 公开素材。@param allowed 可写路径。@param native 原生验收。@param outcomes 结果。
    @param branches 固定分支。@return 任务定义。
    """
    evaluation = {'version': 1, 'rubric': f'verification/{key}.rubric.json'}
    if native is not None:
        evaluation['native'] = native
    return {'id': key, 'kind': kind, 'goal': goal, 'prompt': prompt, 'requires': [],
        'materials': materials or [], 'allowed_paths': allowed or [], 'outcomes': outcomes or ['resolved'],
        'max_turns': 4, 'evaluation': evaluation, 'branches': branches or []}


def main() -> None:
    """生成清洁源码、任务及验收依据草案。@return None。"""
    seed = DRAFT_ROOT / 'seed'
    library = seed / 'library'
    if library.exists():
        raise ValueError('草案源码已存在，拒绝覆盖，请在明确归档后重新生成')
    shutil.copytree(SOURCE_ROOT, library, ignore=shutil.ignore_patterns('.git', '.venv', 'venv',
        '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.coverage', '*.pyc', '*.pyo'))
    (seed / 'app').mkdir(parents=True, exist_ok=True)
    write_text('seed/app/README.md', '本目录保留给用户业务素材、临时复现和输出；未披露的失败文档不在这里。\n')
    weekly = '---\ntitle: 资料整理周报\nauthor: 小林\ntags:\n  - 文档\n  - 图片\n---\n\n本周完成归档，下一步核对目录。\n'
    write_text('materials/weekly.md', weekly)
    write_text('materials/weekly-usage.md', '业务输入 weekly.md 的 UTF-8 原字节随本任务提供。可以在 app/tmp 写临时示例，禁止修改 library。\n'
        '请给一个完整可执行的主程序；可只在答复给出代码，或保存为 app/example.py。程序从当前业务目录读取 weekly.md，写 weekly-reviewed.md。\n'
        '运行环境提供现有 frontmatter，无需安装依赖；不要覆盖原输入。\n')
    write_text('materials/shallow-example.py', 'import frontmatter\n\n'
        'defaults = {"theme": "light", "lang": "zh"}\n'
        'text = "---\\nsettings:\\n  theme: dark\\n---\\n正文"\n'
        'metadata, body = frontmatter.parse(text, settings=defaults)\n'
        'print(metadata)\n')
    write_text('materials/annotated.md', '---\n# 编辑说明\ntitle: "资料"\n---\n正文')
    write_text('materials/poem.txt', '  缩进正文\n\n')
    write_text('materials/format-inputs.md', 'annotated.md 与 poem.txt 是本任务可见业务文件，保留实际 UTF-8 字节。\n'
        'poem.txt 的明确表示为 "  缩进正文\\n\\n"；只讨论当前版本和最小方案，不改库。\n')
    write_text('disclosure/rendering-boundary.md', '我只需要资料字段，网页由别的系统处理。请据当前代码说明边界。\n')
    write_text('disclosure/reproducer.py', 'import frontmatter\n\n'
        'text = "---\\ncontent: 备用摘要\\n---\\n正文"\n'
        'post = frontmatter.loads(text)\n')
    write_text('disclosure/reproducer-error.txt', "TypeError: Post.__init__() got multiple values for argument 'content'\n")
    write_text('disclosure/request-evidence.md', '我还没给失败文件和异常详情，你根据什么确定？请先核实必要材料。\n')
    write_text('disclosure/unavailable.md', '补充情况：我暂时拿不到失败文档、调用代码和完整异常。请先说明目前能判断到哪、还缺什么、之后怎样核实，不要猜定根因。\n')
    write_text('disclosure/preserve-defaults.md', '这份默认值之后还要给别的文档用，能保留原对象内容吗？\n')
    write_text('disclosure/yaml-only.md', '如果先只支持 YAML 文档呢？请收窄推荐范围，仍不实现。\n')
    source = 'library/frontmatter/__init__.py'
    rubrics = {
        'FM-IN-01': [
            criterion('purpose', '说明适合分离、读取、编辑和序列化文档元数据与正文，不杜撰资料管理平台。', [f'{source}:49', f'{source}:176']),
            criterion('data-boundary', '正确区分 Post 的 metadata 项访问与 post.content 正文；说明读取／导出路径，至少给出一个可定位源码依据。', [f'{source}:145', f'{source}:197', f'{source}:296']),
            criterion('rendering', '明确现有调用链不把 Markdown 渲染成网页；不能编造渲染 API 或把候选增强称现成功能。')],
        'FM-IN-02': [
            criterion('runnable-example', '使用当前存在的 API 给出一个完整主程序，读 weekly.md、打印标题和标签、设置 status、写另一路径后再读回；独立原生验证必须通过。'),
            criterion('preservation', '保持 title／author／tags／正文，status 为已校对，原文件字节不变；不承诺 YAML 排版或文档字节保真。'),
            criterion('source-permission', '仅交付咨询示例和业务输出，不改库源码，不把示例当工程能力检查点。')],
        'FM-DG-01': [
            criterion('initial-evidence', '首轮只有 TypeError，不能确定用户根因；有条件假设可以，但不得声称已复现。合理索取最小文档、调用或完整异常时可一次披露足够材料。'),
            criterion('diagnosis-after-disclosure', 'unavailable 入口不要求定位根因，本项按该入口边界满足；diagnose_then_repair／diagnose_only 入口收到复现后，须准确指出合法 content 元数据与 Post 形参冲突，parse 返回字段而 loads 展开重复传参。仅提问不算材料可得分支完成。', [f'{source}:176', f'{source}:306']),
            criterion('workaround-after-disclosure', 'unavailable 入口不要求给未定根因的具体绕行，本项按该入口边界满足；材料已补齐时须给出不丢业务字段的可行临时处理，如 parse 分开取值，或先构造 Post 再更新 metadata，不得只建议删业务字段。'),
            criterion('unavailable-entry', '仅在 unavailable 入口材料明确无法提供时，说明不能定因、缺什么及怎样核实，可结束为 insufficient_information；该结果不能冒充已定位 BUG。'),
            criterion('read-only', '不自动修库，诊断／合法信息不足本身可以独立结束。')],
        'FM-FX-01': [
            criterion('independent-behavior', '受控原生断言全部满足：content／handler 元数据与正文／实际处理器分开保留，读写往返正确，不按唯一补丁样式评分。'),
            criterion('compatibility', '现有 Post 构造、显式 handler 身份、空头部、null 元数据、defaults 覆盖及 to_dict 扁平语义保持。', [f'{source}:176', f'{source}:306']),
            criterion('scope-and-regression', '只修库读取冲突及必要测试／说明，不改业务字段或顺带做其他候选增强；适用严格原生回归通过才接受检查点。')],
        'FM-DG-02': [
            criterion('not-a-bug', '明确这段调用是已存在的浅覆盖，不是解析器漏字段；文档整个 settings 取代默认 settings。', [f'{source}:78', f'{source}:95']),
            criterion('local-workaround', '给出可运行的两个固定字段调用方合并，文档 theme 优先为 dark，默认 lang 保留为 zh；原 defaults 对象不变，不要求通用递归 API。'),
            criterion('existing-api-and-scope', '不把 merge_metadata／MetadataSchema 提案称既有 API，不改库，不交换优先级。')],
        'FM-PL-01': [
            criterion('normalization-facts', '说明 parse 的 strip、CRLF 规范化与 format 的 strip，以及默认 YAML 转普通值后导出不保注释／引号。', [f'{source}:75', 'library/frontmatter/util.py:23', 'library/frontmatter/default_handlers.py:226']),
            criterion('irreversible-loss', '仅换导出 Dumper 无法恢复已丢原始空白和注释，自定义 handler 不等于现成完整无损编辑；区分语义值和原字节。'),
            criterion('feasible-options', '比较调用方保留原文及限制编辑范围，与显式保真模式／往返节点等扩展；说明新增依赖或限制、失败拒改与兼容默认行为，允许多种合理选择。'),
            criterion('minimal-plan', '推荐能落地的最小范围及只改 title 的验证办法，说明未知语法／块标量／锚点／重复键等未承诺边界；不强制第三方库名，不写实现。')],
    }
    for key, criteria in rubrics.items():
        write_json(f'verification/{key}.rubric.json', {'schema': 1, 'task_id': key,
            'criteria': criteria, 'comparison': '按事实、行为和约束，不按关键词、篇幅或参考答案相似度。',
            'source_commit': COMMIT})
    integration = [
        task('FM-IN-01', 'understand', '判断文档资料提取的适用范围与数据边界',
            '我们要从这种 Markdown 周报里提取标题和标签，供资料整理脚本使用。这个项目适合吗？请简要说明数据怎么进出，以及它会不会把 Markdown 渲染成网页。',
            materials=['materials/weekly.md'], branches=[{'id': 'rendering-correction',
                'when': '回答把元数据提取与网页渲染混为一谈，需要一次用户澄清。',
                'materials': ['disclosure/rendering-boundary.md']}]),
        task('FM-IN-02', 'consult', '用现有 API 完成周报读取、更新和另存往返',
            '请给一个最小 Python 用法：读取 weekly.md，打印标题和标签，增加 status 为“已校对”，写到 weekly-reviewed.md，再读回来确认字段和正文都对。不要覆盖原文件。',
            materials=['materials/weekly.md', 'materials/weekly-usage.md'],
            allowed=['app/example.py', 'app/tmp', 'app/weekly-reviewed.md'], native='verification/consult.native.json')]
    diagnostic = task('FM-DG-01', 'diagnose', '先取得必要材料，再判断部分文档的 TypeError 原因',
        '有一部分 Markdown 用这个项目读不进去，报 TypeError。是不是库有 BUG？先帮我判断原因。',
        allowed=['app/tmp'], outcomes=['diagnosed', 'insufficient_information'], branches=[
            {'id': 'minimal-reproducer', 'when': '当前入口不是 unavailable，且模型合理请求最小失败文档、调用方式或完整异常；当前尚未披露复现。',
                'materials': ['disclosure/reproducer.py', 'disclosure/reproducer-error.txt']},
            {'id': 'challenge-certainty', 'when': '当前入口不是 unavailable，复现尚未披露，但模型已无依据确定根因；用户要求说明依据。',
                'materials': ['disclosure/request-evidence.md']}])
    fix = task('FM-FX-01', 'modify', '修复合法保留键元数据的读取冲突并保持兼容',
        '请修复这个读取问题。文档里的 content 是业务摘要字段，要和正文分别保留；handler 也可能是业务字段。现有 Post 构造方式和普通文档用法要继续兼容，请加必要回归验证。\n'
        '完整复现：import frontmatter；text = "---\\ncontent: 备用摘要\\n---\\n正文"；frontmatter.loads(text) 报 TypeError: Post.__init__() got multiple values for argument \'content\'。\n'
        '允许修改 library/frontmatter、相关 tests 与说明；不改变 Post.to_dict 的既有扁平输出合同，不顺带扩展格式保真或深合并。',
        allowed=['library/frontmatter', 'library/tests', 'library/README.md', 'library/docs', 'app/tmp'],
        native='verification/repair.native.json', outcomes=['implemented'])
    shallow = task('FM-DG-02', 'diagnose', '解释默认 settings 的浅覆盖并给局部调用方处理',
        '我希望文档只覆盖 theme，默认的 lang 还能保留，但这段代码返回的 settings 里只有 theme。是不是解析漏字段了？请解释现在的行为，并给一个适合这两个固定字段的调用方处理方式，先别改库。',
        materials=['materials/shallow-example.py'], allowed=['app/tmp'], outcomes=['not_a_bug'],
        native='verification/shallow.native.json', branches=[{'id': 'keep-default-object',
            'when': '模型提供的局部处理原地修改了仍要复用的默认对象。', 'materials': ['disclosure/preserve-defaults.md']}])
    plan = task('FM-PL-01', 'plan', '评估只改标题且保留元数据样式与正文空白的最小方案',
        '编辑者只想改标题，但希望 YAML 注释和引号尽量不动，诗歌正文的缩进和末尾空行也要保留。请根据当前代码评估能做到多少，比较调用方处理和库扩展的办法，并推荐一个最小落地范围。这次先讨论，不写实现。',
        materials=['materials/annotated.md', 'materials/poem.txt', 'materials/format-inputs.md'],
        allowed=['app/tmp'], outcomes=['viable_plan'], branches=[{'id': 'yaml-scope',
            'when': '推荐依赖过宽格式范围且尚未给出只支持 YAML 的可行最小范围，用户收窄需求。',
            'materials': ['disclosure/yaml-only.md']}])
    scenarios = [
        {'id': 'FM-S01', 'title': '栏目周报接入', 'goal': '判断适用范围并取得最小接入用法',
            'default_entry': 'normal', 'entries': [{'id': 'normal', 'task_ids': ['FM-IN-01', 'FM-IN-02']},
                {'id': 'consult_only', 'task_ids': ['FM-IN-02']}], 'tasks': integration},
        {'id': 'FM-S02', 'title': '部分文档读取报错', 'goal': '按材料诊断，并在明确的新请求下修复读取问题',
            'default_entry': 'diagnose_then_repair', 'entries': [
                {'id': 'diagnose_then_repair', 'task_ids': ['FM-DG-01', 'FM-FX-01']},
                {'id': 'diagnose_only', 'task_ids': ['FM-DG-01']},
                {'id': 'unavailable', 'task_ids': ['FM-DG-01'], 'materials': ['disclosure/unavailable.md']},
                {'id': 'repair_only', 'task_ids': ['FM-FX-01']}], 'tasks': [diagnostic, fix]},
        {'id': 'FM-S03', 'title': '默认语言没有生效', 'goal': '排除浅覆盖的 BUG 误判并给调用方处理',
            'default_entry': 'normal', 'entries': [{'id': 'normal', 'task_ids': ['FM-DG-02']}], 'tasks': [shallow]},
        {'id': 'FM-S04', 'title': '只改标题与排版保留', 'goal': '比较保真编辑路径和最小落地范围',
            'default_entry': 'normal', 'entries': [{'id': 'normal', 'task_ids': ['FM-PL-01']}], 'tasks': [plan]},
    ]
    manifest = {'schema': 2, 'project_key': 'python-frontmatter', 'title': 'python-frontmatter 文档资料工作场景',
        'category': '文档处理', 'description': '真实固定版本的接入、诊断、方案与兼容修复；4 场景、6 稳定任务。',
        'seed_digest': snapshot_tree(seed)['digest'], 'environment': 'python-frontmatter-py312',
        'source': {'repository': 'https://github.com/eyeseast/python-frontmatter', 'commit': COMMIT,
            'license_files': ['seed/library/LICENSE']}, 'scenarios': scenarios}
    write_json('project.json', manifest)
    for name, mode, expected in [
        ('consult', 'consult', {'candidate_import': True, 'unique_program': True, 'returncode': 0, 'variant_preserved': True,
            'input_unchanged': True, 'title_printed': True, 'tags_printed': True,
            'metadata': {'title': '资料整理周报', 'author': '小林', 'tags': ['文档', '图片'], 'status': '已校对'},
            'body': '本周完成归档，下一步核对目录。'}),
        ('shallow', 'shallow', {'candidate_import': True,
            'metadata': {'settings': {'theme': 'dark'}}, 'body': '正文',
            'defaults': {'theme': 'light', 'lang': 'zh'}}),
        ('repair', 'repair', {'candidate_import': True, 'content_field': True, 'handler_field': True,
            'combined_fields_roundtrip': True, 'explicit_handler_identity': True, 'old_constructors': True,
            'empty_metadata': True, 'null_content_metadata': True, 'defaults_only': True,
            'document_overrides_default': True, 'load_path_and_stream': True, 'to_dict_unchanged': True}),
    ]:
        specification = {'script': 'verification/native_observe.py', 'args': [mode],
            'python_paths': ['library', 'app'], 'expected': expected, 'resource_profile': 'business'}
        if mode == 'repair':
            specification['regression'] = {'cwd': 'library', 'argv': ['python', '-m', 'pytest', '.',
                '--doctest-modules', '--doctest-glob', 'README.md', '-q', '-ra', '-p', 'no:cacheprovider']}
        write_json(f'verification/{name}.native.json', specification)
    original = (library / 'frontmatter/__init__.py').read_text(encoding='utf-8')
    before = '    return Post(content, handler, **metadata)\n'
    if original.count(before) != 1:
        raise ValueError('固定源码 loads 构造位置不唯一，拒绝猜测补丁')
    repaired = original.replace(before, '    # 先传正文与实际处理器，再写元数据，避免合法业务键与构造形参冲突。\n'
        '    post = Post(content, handler)\n    post.metadata.update(metadata)\n    return post\n')
    patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True), repaired.splitlines(keepends=True),
        fromfile='a/frontmatter/__init__.py', tofile='b/frontmatter/__init__.py'))
    write_text('verification/reference/repair.patch', patch)
    write_text('verification/reference/consult_example.py', '"""用于冻结验收校准的完整周报用法；不是候选答案投放材料。"""\n'
        'import frontmatter\n\n'
        'post = frontmatter.load("weekly.md")\n'
        'print(post["title"])\nprint(post["tags"])\n'
        'original_body = post.content\npost["status"] = "已校对"\n'
        'frontmatter.dump(post, "weekly-reviewed.md")\n'
        'again = frontmatter.load("weekly-reviewed.md")\n'
        'assert again.metadata == post.metadata\nassert again.content == original_body\n')
    old_coverage = REPOSITORY_ROOT / '.deploy/github-100-research/resume-app/python-frontmatter/native-coverage.json'
    shutil.copyfile(old_coverage, DRAFT_ROOT / 'verification/reference/existing-native-coverage.json')
    write_json('environment-profile.draft.json', {'schema': 1, 'id': manifest['environment'], 'adapter': 'python-native',
        'python': '3.12', 'status': 'draft_not_admitted',
        'requirements': ['PyYAML==6.0.3', 'pytest==9.1.1', 'toml==0.10.2', 'pyaml==26.7.0',
            'iniconfig==2.3.1', 'packaging==26.3', 'pluggy==1.7.0', 'Pygments==2.21.0'],
        'runtime_requirements': ['PyYAML==6.0.3'], 'business': None, 'regression': None, 'artifacts': [],
        'evidence': '已有 requirements-frozen.txt；目标镜像资源与离线制品由主会话实际准备，不预填通过。',
        'existing_host_reference': {'python': '3.12.3', 'default_passed': 56, 'strict_doctest_supplement_passed': 11,
            'collection_union': 67}, 'target_runtime': {'business_python_reference': '3.12.15', 'tested_this_draft': False}})
    hashes = {str(path.relative_to(library)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(library.rglob('*')) if path.is_file()}
    write_json('verification/reference/source-files.json', {'commit': COMMIT, 'files': hashes,
        'copied_file_count': len(hashes), 'source_was_not_modified': True})
    print(json.dumps({'project': manifest['project_key'], 'scenarios': len(scenarios),
        'tasks': sum(len(item['tasks']) for item in scenarios), 'copied_files': len(hashes),
        'seed_digest': manifest['seed_digest'], 'native_results': 'not_run'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
