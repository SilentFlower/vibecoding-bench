"""制作产品标识、文件清单和并列表数据的排序任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结不同解析策略的实际例子及稳定平局诊断。@return None。"""
    rows = [
        ('NS-U01', 'understand', '解释标识中的负号策略', 'Compare natsorted(["v-3","v2","v-10"]) with alg=ns.SIGNED. Explain whether the hyphen is punctuation or a numeric sign. No edits.',
            'Default unsigned parsing gives v2,v-3,v-10;SIGNED gives v-10,v-3,v2. Choose whether the business identifier embeds signed numbers or uses a separator. Natural order is controlled by this parsing contract,not an automatically correct domain order.', 'signed_numeric_parsing_changes_the_identifier_order'),
        ('NS-U02', 'understand', '区分数值和版本号排序', 'Compare default and ns.FLOAT on ["p1.10","p1.2","p1.9"]. Compare ns.FLOAT and ns.FLOAT|ns.NOEXP on ["v1e2","v20","v3"]. Explain a version-list versus measurement-list choice. No edits.',
            'Default integer token order is p1.2,p1.9,p1.10;FLOAT treats1.10 as1.1 and gives p1.10,p1.2,p1.9. FLOAT interprets1e2 as100,placing v1e2 last;NOEXP instead gives v1e2,v3,v20. Select a typed version contract or measurement grammar explicitly;FLOAT is not semantic-version precedence.', 'float_and_exponent_flags_are_not_semantic_version_ordering'),
        ('NS-C01', 'consult', '选择文件清单的路径排序策略', 'Compare default and ns.PATH on ["Folder/","Folder (1)/","Folder (10)/"] on the supplied Linux platform. Advise folder-component ordering without inspecting or changing real files.',
            'Default gives Folder (1)/,Folder (10)/,Folder/;PATH gives Folder/ first,then numbered siblings,using path components. Select PATH for the supplied display contract and test extensions and nested paths. Sorting strings does not resolve paths,verify existence or enforce a safe filesystem boundary.', 'path_components_require_explicit_path_sorting_semantics'),
        ('NS-C02', 'consult', '明确字节文件名的解码边界', 'Compare natsorted([b"f10",b"f2"]) with natsorted(["f10","f2"]). Advise an explicit text/byte filename strategy and failure policy. No edits.',
            'Bytes retain lexical f10,f2;decoded strings sort naturally f2,f10. The bytes branch does not parse text numbers as if implicit decoding had occurred. Use a declared codec and explicit decode-error handling if text ordering is intended;preserve original bytes as identity when needed and do not invent a codec from filenames.', 'bytes_are_not_implicitly_decoded_into_natural_text_numbers'),
        ('NS-P01', 'plan', '规划并列字段的一致重排', 'labels=["part10","part2","part1"] and amounts=[100,20,10] describe aligned rows. Inspect index_natsorted(labels) and apply that exact permutation with order_by_index to both sequences,including iter=True. Plan validation and publication. No implementation.',
            'The permutation is[2,1,0],yielding labels part1,part2,part10 and amounts10,20,100 without mutating source. Freeze one input snapshot,validate equal lengths and identity alignment,and apply the same permutation to all fields before publishing. Prefer typed records when feasible;do not sort each column independently or reuse indices after source mutation. iter=True produces a lazy iterator,so consume within the frozen lifetime.', 'one_frozen_index_permutation_preserves_parallel_record_alignment')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('NS-D01', 'diagnose', '诊断前导零平局的顺序变化', 'A report says a1 and a01 change relative order between runs. Request exact input order,algorithm flags,key and output controls before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed controls to distinguish equal natural keys plus stable input order from nondeterministic sorting. An explicit deterministic tie-break/PRESORT can be proposed only with its actual behavior and identity implications. Missing evidence supports insufficient_information;do not claim identifiers are interchangeable or random sorting.', None))
    materials['disclosure/ties.md'] = 'No custom key or flags:input["a2","a1","a01"] gives["a1","a01","a2"];input["a01","a1","a2"] gives["a01","a1","a2"]. Default generated natural keys for a1/a01 are equal. Separate control natsorted(["x1","x01","x001"],alg=ns.PRESORT) gives["x001","x01","x1"],while default preserves the input tie order. There is no source mutation or locale flag.\n'
    materials['disclosure/unavailable.md'] = 'Exact input order,key,algorithm flags and output controls cannot be supplied.\n'
    answers.update({'NS-D01-question': 'Please provide the exact input order,key,algorithm flags and both output controls,including whether leading-zero identifiers have equal generated keys. No edits are authorized.',
        'NS-D01': 'The controls show stable sorting of equal natural keys: a1 and a01 retain their input order,so a changed upstream order changes the tie. Freeze the input order or define a deterministic secondary key. PRESORT first compares strings,as the separate x001,x01,x1 control demonstrates;validate that policy for the business identifiers rather than merging their identities. No random algorithm or package defect is established. No changes.',
        'NS-D01-unavailable': 'Exact input/key/flags and output controls are unavailable. Record insufficient_information and request them later;the ordering cause is not established. No edits.'})
    build_project('natsort', {'title': 'Natsort产品清单工作场景', 'category': '数值解析、路径与稳定重排',
        'description': '符号、浮点和指数语义、路径清单、字节名称、并列数据重排及前导零平局诊断。'}, definitions,
        [('NS-S01', '数值解析策略', '按标识语法选择排序', ['NS-U01', 'NS-U02']),
         ('NS-S02', '文件清单策略', '明确路径与字节边界', ['NS-C01', 'NS-C02']),
         ('NS-S03', '并列数据方案', '共享一份冻结排列', ['NS-P01']),
         ('NS-S04', '稳定平局诊断', '核对实际输入与键', ['NS-D01'])], materials,
        branches={'NS-D01': [{'id': 'equal-natural-keys', 'when': 'Exact input/key/flags and output controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/ties.md']}]},
        extra_entries={'NS-S04': [{'id': 'unavailable', 'task_ids': ['NS-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('natsort-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
