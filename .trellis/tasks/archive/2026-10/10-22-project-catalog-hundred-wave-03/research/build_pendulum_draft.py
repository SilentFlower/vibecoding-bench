"""制作日期调度、时间解释和带类型数据接入的实际任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项日期业务判断，明确原件和本轮构建口径。@return None。"""
    rows = [
        ('PN-U01', 'understand', '解释月份裁剪与连续加法', 'Start datetime(2025,1,31,tz="UTC"). Compare add(months=1),then another month,with add(months=2) from the original. Explain the retained anchor and immutability. No edits.',
            'The first addition clips to February28;another month reaches March28. A single two-month addition from January31 reaches March31,and the original stays January31. Calendar month addition with clipping is not associative. Preserve the intended original day/short-month policy when calculating scheduled dates;do not infer repeated calls retain a hidden31st-day anchor.', 'month_clipping_makes_repeated_addition_differ_from_a_single_combined_addition'),
        ('PN-U02', 'understand', '区分日历月和近似秒数', 'Create duration(months=1),inspect total_seconds(),and compare adding its months versus adding its total_seconds() to UTC January31,2025. Explain the resulting dates and elapsed duration. No edits.',
            'The duration scalar reports30 days of seconds. Applying one calendar month reaches February28,an actual28-day interval;adding the30-day seconds reaches March2. A calendar month is context dependent,so do not serialize it as that scalar and expect identical calendar arithmetic. Preserve typed units and the required arithmetic contract.', 'calendar_months_and_approximate_duration_seconds_are_not_interchangeable'),
        ('PN-C01', 'consult', '选择时区转换或墙钟重新解释', 'From UTC2026-01-01 12:00,compare in_timezone("America/New_York") with set(tz="America/New_York"). Inspect wall hour and integer timestamp. Advise an event-import interpretation contract. No implementation.',
            'in_timezone yields07:00-05:00 at the same instant. set retains12:00 wall fields with the new zone,shifting the instant by+5 hours. Choose conversion for an already known instant and a separately validated interpretation policy for local wall input;do not use set as an instant-preserving conversion.', 'timezone_conversion_preserves_the_instant_while_set_reinterprets_wall_fields'),
        ('PN-C02', 'consult', '明确夏令时重叠和不存在时间策略', 'Compare Europe/Paris2026-10-25 02:30 with fold0 and fold1 by timestamps. Construct Europe/Paris2026-03-29 02:30 with raise_on_unknown_times=True. Advise scheduling input and retained evidence. No edits.',
            'The two02:30 folds are distinct instants one hour apart. The spring02:30 does not exist and explicit raising produces NonExistingTime. Require a named-zone/ambiguity/gap policy,retain original local fields and resolved offset/instant,and request a choice when needed. Do not silently assume one fold or claim wall fields alone identify an instant.', 'ambiguous_folds_are_distinct_instants_and_nonexistent_times_can_be_rejected'),
        ('PN-P01', 'plan', '规划带日期类型的事件数据接入', 'Compare parse("2026-10-22") with exact=True and parse("12:30:00",exact=True). Inspect returned types and default timezone/time imputation. Plan separate date,local-time and instant fields plus validation/publication errors. No implementation.',
            'Ordinary date parsing yields a midnight UTC DateTime;exact=True preserves Date,and the exact time string yields Time. Define expected field types before parsing,require explicit timezone/offset where an instant is needed,and reject or explicitly resolve missing components instead of inventing midnight/UTC semantics. Preserve raw text and normalized typed values and test invalid/ambiguous input. Successful parsing alone does not establish a complete event instant.', 'exact_parsing_preserves_date_and_time_types_instead_of_inventing_an_instant')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made;business probes use actual Python candidate source and complete original Rust/Python collections are recorded separately.'
    definitions.append(('PN-D01', 'diagnose', '诊断解析时区参数未转换结果', 'A parse(...,tz=...) call appears to ignore the requested output zone. Request the full input string,explicit offset,options,returned timezone/timestamp and an in_timezone control before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed offset/parser evidence to distinguish a default interpretation zone from output conversion. Missing controls support insufficient_information;do not erase an explicit offset or claim a timestamp changed without proof.', None))
    materials['disclosure/explicit-offset.md'] = 'parse("2026-01-01T12:00:00+02:00",tz="America/New_York") returns12:00+02:00. Calling in_timezone("America/New_York") on it yields05:00-05:00 with the same timestamp. Parser construction selects parsed.tzinfo before the tz option. No wrapper,local timezone or missing offset is involved.\n'
    materials['disclosure/unavailable.md'] = 'Full input string,offset,parse options,returned zone/timestamp and conversion control are unavailable.\n'
    answers.update({'PN-D01-question': 'Please provide the complete input including offset,all parse options,the actual returned zone/timestamp and an in_timezone control. No edits are authorized.',
        'PN-D01': 'The supplied string already has an explicit+02:00 offset,which parsed.tzinfo preserves ahead of the tz fallback option. That option does not request an output-zone conversion here. Apply the explicit in_timezone conversion for the established instant;the05:00-05:00 control preserves its timestamp. Do not remove the offset or reinterpret the wall clock to force a display zone. No package changes were made.',
        'PN-D01-unavailable': 'The exact string/offset/options and result/control are unavailable. Record insufficient_information and request them later;no precise cause is established. No edits.'})
    licenses = ['seed/library/LICENSE', 'seed/app/babel-2.18-LICENSE.txt', 'seed/app/babel-2.18-LICENSE.unicode.txt']
    root = Path('.deploy/project-catalog-hundred/stage-03/drafts/projects/pendulum')
    licenses += [str(path.relative_to(root)) for path in sorted((root/'seed/app/rust-licenses').rglob('*')) if path.is_file()]
    build_project('pendulum', {'title': 'Pendulum事件时间工作场景', 'category': '月份、时区与数据类型',
        'description': '月份裁剪、日历单位、时区解释、夏令时选择、带类型接入方案及显式偏移诊断。'}, definitions,
        [('PN-S01', '日历算术解释', '保留月份与时间单位', ['PN-U01', 'PN-U02']),
         ('PN-S02', '事件时间咨询', '明确转换和本地时间策略', ['PN-C01', 'PN-C02']),
         ('PN-S03', '带类型接入方案', '区分日期、本地时间和瞬间', ['PN-P01']),
         ('PN-S04', '解析时区诊断', '核显式偏移与输出转换', ['PN-D01'])], materials,
        branches={'PN-D01': [{'id': 'explicit-offset-precedence', 'when': 'Exact input/offset/options and returned zone/timestamp/conversion controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/explicit-offset.md']}]},
        extra_entries={'PN-S04': [{'id': 'unavailable', 'task_ids': ['PN-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=licenses)
    Path(__file__).with_name('pendulum-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
