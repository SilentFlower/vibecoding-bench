"""制作富文本片段、数据提取和规范化输出的真实场景。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结HTML恢复的业务效果及严格模式诊断。@return None。"""
    rows = [
        ('H5-U01', 'understand', '解释表格恢复后的真实树', 'Parse <table>outside<tr><td>A</td></tr></table> with default etree builder and serialize with omit_optional_tags=False. Explain outside text position and tbody insertion. No edits.',
            'The parser creates html/head/body,places outside before the table by foster parenting,and inserts tbody around tr. Extract from the recovered DOM rather than assuming source nesting. Recovery is a defined HTML tree-building behavior,not proof of source validity or lossless formatting preservation.', 'html_table_recovery_moves_text_and_inserts_tbody'),
        ('H5-U02', 'understand', '解释片段的容器上下文', 'parseFragment("<tr><td>A</td></tr>") separately with container="div","table","tbody";serialize with omit_optional_tags=False. Explain a table-fragment ingestion contract. No edits.',
            'div context gives only text A;table context yields tbody/tr/td;tbody context yields tr/td. The same fragment is interpreted by different insertion modes. Use the actual embedding container explicitly and test that context;parseFragment is not context-independent XML parsing.', 'fragment_tree_depends_on_the_declared_container_context'),
        ('H5-C01', 'consult', '明确富文本解析的安全边界', 'Parse and default-serialize the fragment <script>alert(1)</script><p onclick="go()">A</p> without displaying/executing it. Advise a separate rendering policy for supplied untrusted rich text. No implementation.',
            'Default parsing/serialization retains the script and onclick attribute;sanitize defaults False. Tree recovery and serialization therefore do not establish safe rendering. Choose a maintained,explicit allowlist and URL/attribute policy with consumer-specific tests and defense in depth. The supplied control only observes strings,does not execute browser code,and does not justify universal sanitization claims or modifying this package.', 'default_html_parsing_and_serialization_preserve_active_content'),
        ('H5-C02', 'consult', '选择元素查询和文本实体策略', 'Parse <p>Café&nbsp;€</p>;compare .find(".//p") with a query using XHTML namespace. Compare namespaceHTMLElements=False. Advise an extraction representation preserving raw evidence. No edits.',
            'Default HTML elements use http://www.w3.org/1999/xhtml,so the unqualified query misses p while a namespaced query finds it. Text is Café followed by U+00A0 and euro;entity spelling is decoded. Disabling HTML namespaces is an explicit alternative contract. Keep raw input separately if exact entity spelling or formatting matters;do not call a failed unqualified query missing source data.', 'default_html_namespaces_affect_queries_and_entities_decode_to_text'),
        ('H5-P01', 'plan', '规划HTML规范化报告与原文保存', 'Use source <p class=\'x\'>A&nbsp;B</p>. Parse and serialize with omit_optional_tags=False,quote_attr_values="always";reparse and serialize once more. Plan meaningful normalization/roundtrip checks while retaining original input. No implementation.',
            'The control normalizes wrapper elements,quotes and entity text;its second serialization matches the first but neither preserves the input bytes. Freeze parser/builder/serializer options and compare intended DOM/text invariants,plus idempotence over a relevant malformed/Unicode/table corpus. Preserve raw source and errors separately. One successful control is not proof of general losslessness,HTML validity or safe rendering.', 'normalized_serialization_is_stable_for_the_control_and_not_source_preservation')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('H5-D01', 'diagnose', '诊断严格模式为何提前拒绝', 'A strict HTMLParser raises before extracting a paragraph. Request exact input,strict flag,exception and non-strict errors/output before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed parse-error evidence to identify the first strict failure and distinguish recovery mode from a validity checker. Missing controls support insufficient_information;do not blame content loss,encoding or all malformed markup without evidence.', None))
    materials['disclosure/strict.md'] = 'Exact input "<p>x". HTMLParser().parse recovers the paragraph and errors=[((1,3),"expected-doctype-but-got-start-tag",{"name":"p"})]. HTMLParser(strict=True).parse raises ParseError:Unexpected start tag (p). Expected DOCTYPE. No byte decoding or other wrapper is involved. The report only needs paragraph extraction from this supplied fragment-like input.\n'
    materials['disclosure/unavailable.md'] = 'Exact input,strict flag,exception and non-strict errors/output are unavailable.\n'
    answers.update({'H5-D01-question': 'Please provide the complete input,strict flag,exception and non-strict error/output control. I need the first actual parse error before diagnosing;no edits are authorized.',
        'H5-D01': 'The first error is the missing document doctype at the opening p,which strict=True immediately raises as ParseError. The default parser records it and recovers. Choose explicit fragment context or the documented recovery/error-reporting path for this extraction contract;do not infer a complete HTML validity result or silently discard errors. No source changes were made.',
        'H5-D01-unavailable': 'The exact input/mode/error and recovery control are unavailable. Record insufficient_information and request them later;no precise cause is established. No edits.'})
    build_project('html5lib', {'title': 'HTML5lib富文本工作场景', 'category': 'HTML恢复、查询与输出边界',
        'description': '表格恢复、片段上下文、安全边界、命名空间、规范化方案及严格模式诊断。'}, definitions,
        [('H5-S01', '恢复与片段解释', '以实际树为准', ['H5-U01', 'H5-U02']),
         ('H5-S02', '提取和渲染策略', '明确命名空间及安全边界', ['H5-C01', 'H5-C02']),
         ('H5-S03', '规范化输出方案', '保留源文与语义证据', ['H5-P01']),
         ('H5-S04', '严格解析诊断', '取得首个实际错误', ['H5-D01'])], materials,
        branches={'H5-D01': [{'id': 'strict-error-control', 'when': 'Exact input/mode/error and recovery controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/strict.md']}]},
        extra_entries={'H5-S04': [{'id': 'unavailable', 'task_ids': ['H5-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENSE', 'seed/library/html5lib/tests/testdata/LICENSE'])
    Path(__file__).with_name('html5lib-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
