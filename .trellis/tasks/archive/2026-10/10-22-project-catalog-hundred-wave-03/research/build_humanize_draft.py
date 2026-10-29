"""冻结人类可读显示、语言上下文和可复现时间报告的独立任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """制作七个来源明确、各有独立决策的任务。@return None。"""
    rows = [
        ('HU-U01', 'understand', '解释容量展示的三种单位', 'Compare naturalsize(1000), naturalsize(1000,binary=True), naturalsize(1024,binary=True) and naturalsize(1024,gnu=True). Explain bases, suffixes and the GNU precedence. No edits.',
            'The outputs are 1.0 kB, 1000 Bytes, 1.0 KiB and 1.0K. Decimal uses1000; binary/GNU use1024, with distinct suffix/spacing, and GNU takes precedence over binary. Select an explicit display convention; do not relabel decimal and binary quantities as interchangeable.',
            'decimal_binary_and_gnu_units_are_distinct'),
        ('HU-U02', 'understand', '解释持续时长展示丢失的信息', 'Compare precisedelta(-90) and precisedelta(90); also render timedelta(hours=49,seconds=33.12) with suppress=["days"] and 0.1 with minimum_unit="minutes". Explain what can be recovered from the display. No edits.',
            'Both signed inputs render 1 minute and 30 seconds because this is an absolute distance display. Suppressing days renders49 hours and33.12 seconds;0.1 seconds at minutes resolution renders0 minutes. Preserve original signed numeric duration separately; display text does not preserve sign or sub-resolution data.',
            'duration_display_discards_sign_and_can_suppress_units'),
        ('HU-U03', 'understand', '解释相对时间的输入类型与时态', 'Fix when=datetime(2026,1,1,12). Compare naturaltime(60,future=True,when=when), naturaltime(timedelta(seconds=60),future=True,when=when) and naturaltime(when+timedelta(seconds=60),when=when). Explain tense and reproducibility. No edits.',
            'They render a minute from now, a minute ago, and a minute from now. Numeric future flag selects tense, while datetime/timedelta derive tense from the represented date and ignore that flag. Pass one explicit reference instant for the report and retain the original timestamps; do not rely on repeated implicit now calls.',
            'tense_depends_on_the_input_type_and_fixed_reference'),
        ('HU-C01', 'consult', '明确本地化数字与输入校验边界', 'Activate de_DE and compare intcomma(1234.5,2) with intcomma("1.234,50",2). Deactivate and render intcomma("not a number"). Advise a report ingestion contract without implementing it.',
            'Both German controls yield1.234,50. The string path strips the active thousands separator and normalizes its decimal separator. Invalid text is returned unchanged, so success returning a string does not establish numeric validity. Validate typed machine data separately, select locale explicitly for display, and preserve raw values and validation failures.',
            'localized_text_formatting_is_not_input_validation'),
        ('HU-C02', 'consult', '避免用容量展示反推账单数据', 'Compare naturalsize(999999) and naturalsize(1000000), then naturalsize(0.9). Advise whether to store/compare these display strings for precise usage or billing. No implementation.',
            'Both large values display1.0 MB after rounded mantissa promotion;0.9 displays0 Bytes by integer truncation below the unit base. These are lossy human-facing strings. Keep exact typed units and values for comparisons/usage calculations and format at the presentation boundary; no billing rule or validated monetary policy is supplied.',
            'rounded_display_is_lossy_and_not_a_storage_quantity'),
        ('HU-P01', 'plan', '规划协程中的语言上下文隔离', 'One event loop runs task A:activate("de_DE");signal ready;await switched;read decimal_separator(). Task B:await ready;deactivate();signal switched;read decimal_separator(). Both run on one thread. Plan safe per-report language handling based on actual state storage. No library or application edits.',
            'Both read a dot after B deactivates: _CURRENT is threading.local, shared by async tasks on the same thread, not ContextVar. Plan a serialized synchronous formatting block with explicit activate/cleanup and no await, or a separately validated task-context adapter. Test event-controlled interleavings, errors, nested use and thread separation. Do not claim existing async task isolation or authorize a package change.',
            'thread_local_translation_state_is_shared_between_async_tasks')]
    materials, definitions, answers = {}, [], {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('HU-D01', 'diagnose', '诊断切换翻译目录未生效',
        'A language catalog path change appears ineffective. Request the exact locale, activation order, paths, object identity and a fresh-process control before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed activation/cache evidence to locate the path selection boundary. A previously cached locale can reuse its translation without inspecting the later path. Separate process initialization and a proposed explicit cache strategy; missing controls support insufficient_information. Do not clear private globals or promise a new catalog was loaded.', None))
    materials['disclosure/cache.md'] = 'In one fresh process activate("de_DE") with the supplied compiled default catalog; then activate("de_DE","/no-such-catalog"). Both calls return the identical translation object and the second call does not raise. In a separate fresh process, the invalid path as first activation raises FileNotFoundError. No wrapper or cache mutation is present. Diagnose the supplied i18n._TRANSLATIONS lookup and path handling. No edits.\n'
    materials['disclosure/unavailable.md'] = 'The exact locale, activation order, paths, returned object identity and fresh-process control are unavailable.\n'
    answers.update({'HU-D01-question': 'Please provide the exact locale, activation order, both paths, returned object identity and an isolated fresh-process control. I cannot assign a cause from the symptom alone.',
        'HU-D01': 'The complete controls establish a locale cache hit: _TRANSLATIONS is keyed only by locale. After the first de_DE activation, the later path is not searched and the same object is reused; a missing directory therefore need not raise. A fresh first activation uses the path and fails. Arrange catalog selection at controlled process initialization or separately design/test an explicit cache lifecycle. No private cache clearing or source patch is authorized.',
        'HU-D01-unavailable': 'The activation/cache controls are unavailable. Record insufficient_information and request them when possible; a path/cache cause has not been established. No edits.'})
    build_project('humanize', {'title': 'Humanize报表展示工作场景', 'category': '单位、时态与语言上下文',
        'description': '明确容量和时长显示、相对时态、数字本地化、精度损失及协程语言状态。'}, definitions,
        [('HU-S01', '容量展示与精度', '确定单位并保留机器数值', ['HU-U01', 'HU-C02']),
         ('HU-S02', '可复现时间报告', '区分距离和时态', ['HU-U02', 'HU-U03']),
         ('HU-S03', '报表本地化', '隔离校验与语言状态', ['HU-C01', 'HU-P01']),
         ('HU-S04', '翻译目录诊断', '核对初始化和缓存证据', ['HU-D01'])], materials,
        branches={'HU-D01': [{'id': 'catalog-cache-order', 'when': 'Exact activation sequence, locale, paths, identity and fresh-process controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/cache.md']}]},
        extra_entries={'HU-S04': [{'id': 'unavailable', 'task_ids': ['HU-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENCE'])
    Path(__file__).with_name('humanize-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
