"""制作主题颜色导入、校验和往返数据策略的实际任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项颜色业务判断，不捏造颜色相似度或完整CSS解析。@return None。"""
    rows = [
        ('WC-U01', 'understand', '解释命名颜色的规范范围', 'Compare name_to_hex("orange",spec="html4") and spec="css21";also name_to_hex("GRAY",spec="css3"). Explain membership and case normalization. No edits.',
            'orange is rejected in html4 but resolves to #ffa500 in css21;GRAY resolves to #808080 because names are lowercased. Pin an explicit supported name specification for theme imports;do not assume all browser color syntax or all named colors belong to each set.', 'named_color_membership_depends_on_the_explicit_specification'),
        ('WC-U02', 'understand', '区分简写归一化与严格颜色格式', 'Compare normalize_hex("#AbC"), html5_parse_simple_color("#abc") and html5_parse_simple_color("#aabbcc"). Explain the accepted representations. No edits.',
            'normalize_hex expands/lowercases #AbC to #aabbcc. HTML5 simple parsing requires exactly # plus six ASCII hex digits and rejects #abc;the full form yields170,187,204. Pick the input contract explicitly;these functions do not parse arbitrary CSS rgba(),alpha hex or keywords.', 'hex_normalization_and_html5_simple_validation_have_distinct_input_contracts'),
        ('WC-C01', 'consult', '明确通道越界时的拒绝策略', 'Compare normalize_integer_triplet((300,-5,128)) and rgb_to_hex((300,-5,128)). Advise a strict theme-upload validation contract without implementing it.',
            'The functions clip to255,0,128 and emit #ff0080 instead of rejecting the out-of-range channels. Clipping is normalization,not proof input was valid. Validate channel types/ranges separately if rejection is required,and preserve raw input and the chosen normalization policy for error reporting.', 'integer_rgb_normalization_clips_invalid_channels_instead_of_rejecting'),
        ('WC-C02', 'consult', '避免历史兼容算法接受无效颜色', 'Compare html5_parse_legacy_color("chucknorris") with html5_parse_simple_color("chucknorris"). Advise whether legacy parsing should validate new theme settings. No edits.',
            'Legacy browser recovery produces192,0,0 from chucknorris while simple parsing rejects it. The forgiving legacy algorithm targets old malformed HTML behavior;using it as a validator silently accepts junk. Choose a strict declared representation for new settings and isolate any explicitly required legacy migration path.', 'legacy_browser_color_recovery_is_not_strict_color_validation'),
        ('WC-P01', 'plan', '规划颜色规范化与原始值保存', 'Convert ("30%","50%","70%") to integer RGB and back to percentages. Compare aqua/cyan to hex and reverse #00ffff to a name. Plan theme storage,display and audit fields with explicit precision/alias policy. No implementation.',
            'The integer result is76,128,178 (ties use Python round);reverse percentages are29.80%,50%,69.80%. aqua and cyan map to the same #00ffff,whose canonical reverse name is cyan. Store the chosen normalized color value plus original text/representation and explicit spec/version when audit or spelling matters;percentage conversion quantizes and reverse lookup cannot preserve alias identity. Define alpha handling separately because these RGB triplets have no alpha channel.', 'percentage_conversion_quantizes_and_named_reverse_lookup_loses_alias_spelling')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('WC-D01', 'diagnose', '诊断CSS4颜色往返不一致', 'A named-color roundtrip rejects rebeccapurple. Request pinned version,exact forward/reverse calls,spec and exception before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed fixed-source evidence to distinguish unsupported specification from an inconsistent forward registry. Missing controls support insufficient_information. A source repair requires its own authorization;do not invent a public CSS4 constant or claim this pinned implementation already supports the forward lookup.', None))
    materials['disclosure/css4-registry.md'] = 'Pinned source:hex_to_name("#663399",spec="css4") returns "rebeccapurple",but name_to_hex("rebeccapurple",spec="css4") raises ValueError. _CSS4_NAMES_TO_HEX includes the name,while _names_to_hex maps CSS4 to _CSS3_NAMES_TO_HEX;the reverse registry uses _CSS4_HEX_TO_NAMES. Public __init__ does not export CSS4;the supplied call passes literal "css4". No external CSS parser or cache is involved.\n'
    materials['disclosure/unavailable.md'] = 'Pinned version,exact forward/reverse calls,spec and exception are unavailable.\n'
    answers.update({'WC-D01-question': 'Please provide the pinned version,exact forward and reverse calls,spec and exception. No edits are authorized;I need the actual lookup path.',
        'WC-D01': 'The supplied source has asymmetric registry wiring:the CSS4 forward registry points to the CSS3 name map despite a defined CSS4 map,while the reverse uses the CSS4 map. That explains this exact roundtrip failure;it is not an unsupported-spec error or proof the source lacks the name definition. Report a separately scoped registry repair and regression controls,or use an explicit validated normalized hex representation for the present workflow. Do not invent a public CSS4 export. No changes were made.',
        'WC-D01-unavailable': 'The exact version/calls/spec/exception are unavailable. Record insufficient_information and request them when possible;no precise source cause is established.'})
    build_project('webcolors', {'title': 'Webcolors主题颜色工作场景', 'category': '颜色规范、校验与往返数据',
        'description': '命名范围、简写和严格格式、通道裁剪、历史恢复、量化与别名策略及注册表诊断。'}, definitions,
        [('WC-S01', '颜色输入合同', '按规范选择表示', ['WC-U01', 'WC-U02']),
         ('WC-S02', '颜色校验咨询', '区分归一化与严格拒绝', ['WC-C01', 'WC-C02']),
         ('WC-S03', '颜色存储方案', '保留原值、精度与别名', ['WC-P01']),
         ('WC-S04', '颜色注册表诊断', '核对真实往返路径', ['WC-D01'])], materials,
        branches={'WC-D01': [{'id': 'css4-forward-registry', 'when': 'Exact pinned version,calls,spec and exception have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/css4-registry.md']}]},
        extra_entries={'WC-S04': [{'id': 'unavailable', 'task_ids': ['WC-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('webcolors-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
