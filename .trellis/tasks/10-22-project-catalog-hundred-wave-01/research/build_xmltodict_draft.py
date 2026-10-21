"""根据已核XML源码制作订单交换草稿，保留其他草稿和完整原版。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import snapshot_tree


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'
PROJECT = WORKSPACE / 'drafts/projects/xmltodict'
REVISION = '6e29fba282e68631034dd2722a413b4e35276584'


def write(relative: str, content: str | dict) -> None:
    """写入独占XML草稿。@param relative 相对路径。@param content 文本或JSON。@return None。"""
    path = PROJECT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n'
        if isinstance(content, dict) else content, encoding='utf-8')


def main() -> None:
    """制作五场景十一项独立任务及真实材料。@return None。"""
    if (PROJECT / 'project.json').exists():
        raise ValueError('XML草稿已存在，拒绝覆盖')
    write('materials/order-single.xml', '<orders><order id="A"><qty>2</qty><label>咖啡</label></order></orders>\n')
    write('materials/order-many.xml', '<orders><order id="A"><qty>2</qty></order><order id="B"><qty>3</qty></order></orders>\n')
    write('materials/import-requirements.md', 'Import local order XML. Require a nonempty unique order ID and a positive integral quantity. Report malformed XML separately from missing or invalid business fields. Choose a deliberate duplicate-ID and commit policy; no database or external service is required for this planning task. XML parsing alone must not be described as business-schema validation or automatic numeric conversion.\n')
    write('materials/missing-key.md', 'An order import raises KeyError while reading a field. The actual XML, parse options and failing dictionary access have not been provided. Do not assume an empty element, spelling error or namespace cause from this symptom alone.\n')
    namespace_xml = '<o:orders xmlns:o="urn:bench:orders"><o:order id="A"><o:qty>2</o:qty></o:order></o:orders>\n'
    namespace_call = '''import xmltodict

xml = open("order-namespaced.xml", encoding="utf-8").read()
document = xmltodict.parse(xml, process_namespaces=True)
print(document["orders"]["order"]["qty"])
'''
    write('disclosure/order-namespaced.xml', namespace_xml)
    write('disclosure/namespace-call.py', namespace_call)
    write('disclosure/namespace-error.md', 'The supplied call raises KeyError: orders. This is the exact XML and call used; no postprocessor or custom namespace mapping is installed.\n')
    write('disclosure/unavailable.md', 'The actual XML, parse options and failing access cannot be provided. No further incident evidence is available.\n')
    write('materials/order-namespaced.xml', namespace_xml)
    write('materials/namespace-call.py', namespace_call)
    write('materials/empty-output.py', '''from xmltodict import unparse

print(unparse({"root": {"omitted": [], "none": None, "explicit": [None], "text": [""]}}))
''')
    write('materials/mixed.xml', '<p>before<b>bold</b>after<i>italic</i>end</p>\n')
    write('materials/roundtrip-requirements.md', 'A publishing workflow asks whether parse followed by unparse preserves mixed-content order, whitespace and original namespace prefixes byte for byte. Inspect the supplied mixed-content document and actual model. Distinguish semantic data extraction from lexical document editing. Do not promise lossless XML editing or require a library repair for an unpromised guarantee.\n')
    write('materials/chunk-input.py', '''from xmltodict import parse

chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "</orders>"]
print(parse(chunk for chunk in chunks))
print(parse(iter(chunks)))
''')
    write('materials/iterator-contract.md', '''Extend parse to accept ordinary synchronous Iterator objects of XML text or byte chunks (including list_iterator, map and a custom __iter__/__next__ object), preserving existing generator behavior. This is an explicit input enhancement, not a claim that every iterable was already supported.
Keep the public signature and dependencies. Preserve complete str/bytes/bytearray/memoryview inputs, file-like read precedence, namespace options and existing defaults. Decode UTF-8 split across byte chunks through the existing parser. Do not first join or materialize the complete source.
Preserve TypeError for invalid chunks, source iteration exceptions, finalization errors for truncated XML, and immediate ParsingInterrupted when item_callback returns false. Do not consume later chunks after that rejection. Ordinary list containers and asynchronous inputs are outside this enhancement.
Only library/xmltodict.py and library/tests/test_xmltodict.py may change. Add meaningful public tests that fail on the pinned original and pass after the enhancement. Preserve all frozen original regression tests and pytest controls.
''')
    write('materials/stream-orders.py', '''from xmltodict import parse

received = []

def accept(path, item):
    """保存已处理订单。@param path 当前路径。@param item 订单。@return 是否继续。"""
    received.append((tuple(name for name, attributes in path), item))
    return True

chunks = ["<orders>", "<order id='A'><qty>2</qty></order>", "<order id='B'><qty>3</qty></order>", "</orders>"]
returned = parse((chunk for chunk in chunks), item_depth=2, item_callback=accept)
print(returned, received)
''')
    write('materials/stream-plan.md', 'Process a local sequence of order elements with bounded retained application state. Validate each order and stop on the first rejected item. Explain item_depth, callback return, source consumption and why one very large individual item can still require memory. Choose and state whether already processed orders are committed, staged or rolled back; parsing itself does not provide transaction atomicity. Do not add a service or implement a new parser API.\n')

    definitions = [
        ('XD-U01', 'understand', '解释订单属性、文本及单多结构',
            'Trace both supplied order XML documents through the pinned default parser. Explain attribute names, text and quantity types, and why a single order and repeated orders have different Python shapes. Do not edit files.',
            ['materials/order-single.xml', 'materials/order-many.xml'], 'explained',
            'Explain the actual @id attribute, string quantity and singleton-dict versus repeated-list shape. Do not invent automatic numeric conversion or a forced list under defaults.',
            ['attribute_text_shape', 'single_multiple_shape']),
        ('XD-C01', 'consult', '用已有force_list统一订单集合',
            'Recommend an existing API policy that exposes orders as a list for both supplied documents. Compare force_list names and a path-aware callable without making every XML node a list. Decide whether a library modification is needed.',
            ['materials/order-single.xml', 'materials/order-many.xml'], 'advice_no_code_change',
            'Use the real force_list tuple or callable API with the correct path/key semantics. Provide a valid policy for the supplied orders and preserve unrelated element shapes; no library change is required.',
            ['existing_force_list']),
        ('XD-P01', 'plan', '规划订单解析与业务验证边界',
            'Plan an order-import validation workflow for the supplied business requirements. Separate XML syntax, shape normalization, required IDs, positive integral quantities, duplicate handling and commit policy. Use existing parsing APIs; do not implement a library change.',
            ['materials/order-single.xml', 'materials/import-requirements.md'], 'viable_plan_no_library_change',
            'Separate successful XML parsing from application schema and numeric validation, use a deliberate normalized order shape, and explain duplicate and commit policies without claiming the parser supplies them.',
            ['attribute_text_shape', 'business_validation_separate']),
        ('XD-D01', 'diagnose', '先取完整解析证据再判断缺字段',
            'Investigate the supplied KeyError symptom. Request the actual XML, parse options and failing access or an equivalent minimal reproduction before assigning a cause. Diagnose only evidence actually supplied later. If it cannot be supplied, state the limit and a concrete evidence plan. Do not edit files.',
            ['materials/missing-key.md'], 'diagnosed_no_code_change',
            'The initial symptom is insufficient. Request actual input, parsing options and failing access. Derive a supported diagnosis only after disclosure; insufficient_information is legitimate when the conversation explicitly states the evidence is unavailable. Never invent undisclosed XML or options.', None),
        ('XD-C02', 'consult', '用URI映射稳定命名空间业务键',
            'Using the complete supplied namespace reproduction, explain the actual dictionary keys with process_namespaces enabled. Recommend a valid existing URI mapping to a short namespace or to no namespace, explain collision tradeoffs, and decide whether the library needs modification.',
            ['materials/order-namespaced.xml', 'materials/namespace-call.py'], 'advice_no_code_change',
            'Ground the answer in expanded URI keys and the actual namespaces mapping API. Distinguish URI identity from arbitrary XML prefixes and disclose potential collisions when removing namespaces; do not promise lexical prefix preservation.',
            ['uri_keys_are_observed', 'existing_namespace_mapping']),
        ('XD-U02', 'understand', '区分空列表省略与显式空元素',
            'Explain which XML elements the supplied unparse call actually writes for [], None, [None] and [""]. Distinguish an omitted element from an explicit empty element. Do not edit the library.',
            ['materials/empty-output.py'], 'explained',
            'Explain that the empty list emits no child, while None, [None] and [""] produce explicit empty children in this mapping. Ground the distinction in actual XML, without equating all empty values.',
            ['empty_list_omitted', 'explicit_empty_elements']),
        ('XD-C03', 'consult', '判断混合内容与词法保真需求',
            'Assess the supplied publishing roundtrip requirement and mixed-content document. Compare actual parse/unparse behavior with byte-for-byte preservation of order, whitespace and prefixes. Explain whether existing xmltodict guarantees suffice and recommend an appropriate application/tool boundary.',
            ['materials/mixed.xml', 'materials/roundtrip-requirements.md'], 'advice_with_limits',
            'Demonstrate or correctly explain the mixed-content order limitation and distinguish data-oriented mappings from lexical XML editing. Do not claim byte-perfect preservation, silently strip meaningful mixed text, or label an unpromised guarantee a defect requiring a patch.',
            ['mixed_content_not_lexical_roundtrip']),
        ('XD-D02', 'diagnose', '定位普通分块迭代器的输入分派差异',
            'Trace the complete chunk-input reproduction. Explain why the generator succeeds and the ordinary list_iterator raises TypeError in the pinned parse implementation. Locate the dispatch boundary and describe the requested behavior as an input enhancement, preserving the successful input path. Do not edit files.',
            ['materials/chunk-input.py'], 'diagnosed',
            'Identify the generator-only dispatch versus whole-document fallback for an ordinary Iterator. Keep generator and ordinary iterable/iterator distinctions accurate; do not claim that every iterable or asynchronous input was already supported.',
            ['generator_input_preserved', 'ordinary_iterator_rejected_original']),
        ('XD-M01', 'modify', '支持同步分块Iterator并保留消费边界',
            'Implement the complete public synchronous Iterator enhancement. Preserve the exact existing input, error, callback and namespace contracts, and avoid whole-source buffering. Modify only the authorized implementation and public test file; add meaningful public original-failing tests.',
            ['materials/chunk-input.py', 'materials/iterator-contract.md'], 'implemented',
            'Satisfy the public Iterator input contract and actual source-consumption boundaries while retaining full frozen upstream regression. Preserve complete buffers, files, generators, options and failures; no new dependencies, pytest controls or whole-source join/list buffering.',
            ['generator_input_preserved', 'ordinary_iterators_supported', 'utf8_boundaries_preserved',
                'whole_document_inputs_preserved', 'iterator_errors_preserved',
                'callback_stops_iterator', 'namespace_options_preserved']),
        ('XD-C04', 'consult', '区分分块输入、逐项回调与返回值',
            'Explain the supplied streamed order call: which items reach the callback, what parse returns, how item_depth chooses the item boundary, and how a false callback stops parsing. Does chunked input by itself make parse return a lazy order iterator? Do not edit files.',
            ['materials/stream-orders.py'], 'explained_with_limits',
            'Explain the actual two order callbacks and normal None return at item_depth=2; false causes ParsingInterrupted and stops later source consumption. Do not invent a returned lazy record iterator or equate network chunks with record boundaries.',
            ['item_callbacks_observed', 'callback_stops_source']),
        ('XD-P02', 'plan', '规划有界逐项验证与中止策略',
            'Plan the local bounded order-processing workflow described in the supplied materials. Cover item_depth/callback, per-item validation, source stopping, memory limits and partial versus atomic commit. Use existing APIs without implementing a library change.',
            ['materials/stream-orders.py', 'materials/stream-plan.md'], 'viable_plan_no_library_change',
            'Give a workable callback-based plan and explicit commit semantics. A callback may validate and stop with ParsingInterrupted, but parser streaming alone does not roll back prior effects or bound the size of one individual item.',
            ['item_callbacks_observed', 'callback_stops_source'])]
    tasks = {}
    for identifier, kind, goal, prompt, materials, outcome, requirement, fields in definitions:
        task = {'id': identifier, 'kind': kind, 'goal': goal, 'prompt': prompt,
            'requires': [], 'materials': materials, 'allowed_paths': [], 'outcomes': [outcome],
            'max_turns': 4, 'evaluation': {'version': 1,
                'rubric': 'verification/' + identifier + '.rubric.json', 'semantic': True}, 'branches': []}
        criteria = [{'id': 'business', 'requirement': requirement, 'evidence': []},
            {'id': 'scope', 'requirement': 'Use actual supplied materials and pinned source, respect authorization and distinguish observed behavior, existing guarantees and proposals.', 'evidence': []}]
        if kind == 'modify':
            task['allowed_paths'] = ['library/xmltodict.py', 'library/tests/test_xmltodict.py']
            for criterion in criteria:
                criterion['allow_candidate_evidence'] = True
            criteria.append({'id': 'public-tests', 'requirement': 'Deliver meaningful public regression tests in the authorized test file that fail on the pinned original and pass after the enhancement; cite the actual implementation and test files.', 'evidence': [], 'allow_candidate_evidence': True})
        if identifier == 'XD-D01':
            task['outcomes'].append('insufficient_information')
            task['branches'] = [{'id': 'parse-evidence', 'when': 'The actual XML, parse options and failing access have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests them or an equivalent sufficient reproduction. Supply the complete reproduction together.',
                'materials': ['disclosure/order-namespaced.xml', 'disclosure/namespace-call.py', 'disclosure/namespace-error.md']}]
        if fields is not None:
            native = {'script': 'verification/native_observe.py', 'args': [identifier],
                'python_paths': ['library', 'app'], 'expected': {'candidate_import': True,
                    **{field: True for field in fields}}, 'resource_profile': 'business'}
            if kind == 'modify':
                native['regression'] = {'runner': 'verification/native_regression.py', 'contract': 'verification/native-contract.json'}
            write('verification/' + identifier + '.native.json', native)
            task['evaluation']['native'] = 'verification/' + identifier + '.native.json'
        write('verification/' + identifier + '.rubric.json', {'schema': 1, 'task_id': identifier,
            'source_commit': REVISION, 'criteria': criteria,
            'comparison': 'Accept equivalent correct reasoning and implementations; do not match wording or a reference answer.'})
        tasks[identifier] = task
    scenes = []
    for identifier, title, goal, selected in [
        ('XD-S01', '订单数据的结构与业务校验', '识别真实解析形状和业务验证边界', ['XD-U01', 'XD-C01', 'XD-P01']),
        ('XD-S02', '缺字段诊断与命名空间映射', '先取实际证据再选择已有命名空间能力', ['XD-D01', 'XD-C02']),
        ('XD-S03', '空元素输出与XML保真', '区分数据模型和词法文档需求', ['XD-U02', 'XD-C03']),
        ('XD-S04', '同步分块输入与消费控制', '独立诊断和增强普通分块Iterator', ['XD-D02', 'XD-M01']),
        ('XD-S05', '逐条订单回调与导入策略', '明确流式消费、停止和提交边界', ['XD-C04', 'XD-P02'])]:
        entries = [{'id': 'normal', 'task_ids': selected}]
        if identifier == 'XD-S02':
            entries.extend([{'id': 'diagnose_only', 'task_ids': ['XD-D01']},
                {'id': 'unavailable', 'task_ids': ['XD-D01'], 'materials': ['disclosure/unavailable.md']}])
        if identifier == 'XD-S04':
            entries.extend([{'id': 'diagnose_only', 'task_ids': ['XD-D02']},
                {'id': 'modify_direct', 'task_ids': ['XD-M01']}])
        scenes.append({'id': identifier, 'title': title, 'goal': goal,
            'default_entry': 'normal', 'entries': entries, 'tasks': [tasks[key] for key in selected]})
    shutil.copyfile(Path(__file__).with_name('xmltodict-native-observe.py'), PROJECT / 'verification/native_observe.py')
    write('project.json', {'schema': 2, 'project_key': 'xmltodict', 'title': 'XML订单交换工作场景',
        'category': '结构化数据与流式导入', 'description': '固定真实XML源码上的订单结构、取证、命名空间、输出保真和分块读取；五场景十一任务。',
        'seed_digest': snapshot_tree(PROJECT / 'seed')['digest'], 'environment': 'xmltodict-py312',
        'source': {'repository': 'https://github.com/martinblech/xmltodict', 'commit': REVISION,
            'license_files': ['seed/library/LICENSE']}, 'scenarios': scenes})
    catalog_path = WORKSPACE / 'drafts/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    if 'xmltodict' in catalog['projects']:
        raise ValueError('XML草稿重复注册')
    catalog['projects'].append('xmltodict')
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'draft_project': 'xmltodict', 'scenarios': len(scenes), 'tasks': len(tasks),
        'formal_catalog_modified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
