"""制作Rich客户字段、终端布局、输出缓冲与异常分享任务。"""
from draft_content import build_project


def main() -> None:
    """保存四场景七个独立业务结果，现有能力不另算修复目标。@return None。"""
    materials = {
        'materials/literal-fields.md': 'An invoice description must display the exact customer string [red]urgent[/red], including brackets. Compare default Console.print, print(markup=False) and escape(customer_text) inside a trusted bold Item: prefix. Use synthetic StringIO, disable highlighting/emoji for the complete comparison, and preserve the original value. No project changes are authorized.\n',
        'materials/terminal-output.md': 'Compare the exact text ready styled bold red on (1) a StringIO console with force_terminal=False, (2) force_terminal=True,color_system=standard,no_color=True, and (3) force_terminal=True,color_system=None. No ambient color environment is present. A downstream plain-text parser rejects every ANSI sequence; does no_color alone meet that requirement? No files may be changed.\n',
        'materials/narrow-report.md': 'With width4 print the exact source text 茶tea. Compare Python len with rich.cells.cell_len. Separately print ABCDEFGHIJK at width8 with record=True,no_wrap=True,overflow=ellipsis, then export_text. The full identifier is needed for canonical reconciliation while the narrow display may abbreviate it. Choose ownership for original values versus rendered artifacts; do not edit files.\n',
        'materials/capture.md': 'Create Console(file=a_StringIO,record=False), capture a print of captured inside with console.capture() as capture, then inspect capture.get(), the destination stream and export_text. Explain local test capture versus recorded artifact export. No files may be changed.\n',
        'materials/artifact-symptom.md': 'The invoice appeared in terminal output, but a later HTML artifact lacks its content. Actual Console construction, rendering/export call sequence, clear parameters and original outputs are not supplied. Investigate before deciding the cause.\n',
        'disclosure/exports.md': 'Complete synthetic sequence: Console(file=StringIO(),record=True,force_terminal=False); console.print("invoice-marker"); text=console.export_text(); html=console.export_html(). No clear argument was supplied to either export. The text contains the marker; the later HTML has its document scaffold but not the marker.\n',
        'disclosure/unavailable.md': 'Console settings, export order, clear arguments and complete output are unavailable. No further reproduction can be supplied.\n',
        'materials/multiple-artifacts.md': 'A report renders <invoice> once and needs both text and HTML from that same recorded output. Plan explicit record ownership, clear=False/true lifecycle, escaping expectations and limits of already cropped output. Distinguish capture from record; do not write output files or implement a new exporter.\n',
        'materials/diagnostic-policy.md': 'A synthetic diagnostic raises ValueError("synthetic-message-marker"). Compare print_exception(show_locals=False,extra_lines=0) with the claim that hiding locals makes all output safe to share. The support report needs useful failure type/context but must apply an explicit application policy to sensitive exception messages, paths and original values. No actual token, account, external log or production data is supplied. Plan with existing capabilities; do not send messages or deploy anything.\n'}
    definitions = [
        ('RH-C01', 'consult', '让客户字段按字面显示并保留可信前缀样式',
            'Meet the complete invoice-description requirement with existing APIs. Compare actual default, literal and escaped mixed-markup output and define who owns formatting. Do not modify files or claim bracket escaping strips every possible terminal control.',
            ['materials/literal-fields.md'], 'advice_no_code_change',
            'Default markup renders urgent without the bracket tags. markup=False preserves the complete original string; escape(customer_text) preserves it when mixed into trusted Item formatting. Keep raw business values separately and own highlighting/emoji behavior explicitly. Markup escaping is not a universal ANSI/control-character sanitizer.', ['literal_text_requires_explicit_markup_ownership']),
        ('RH-U01', 'understand', '区分关闭颜色和完全不输出终端控制序列',
            'Trace all three complete terminal-output controls and answer the plain-text parser requirement. Explain automatic/deliberate terminal behavior without assuming real TTY or environment settings beyond those supplied.',
            ['materials/terminal-output.md'], 'explained',
            'Forced nonterminal and color_system=None yield plain ready newline. A forced terminal with no_color=True removes color but can retain bold ANSI styling, so it does not guarantee no ANSI sequences. Explicit plain output must disable the color/style emission path rather than treating no_color as a universal plain-text switch.', ['no_color_can_keep_non_color_terminal_styles']),
        ('RH-C02', 'consult', '分离窄屏展示宽度和完整业务标识',
            'Recommend a current-API layout/artifact policy for the complete Unicode and cropped-ID examples. Give actual width/wrapping and explain what record/export can recover. No implementation or source-data changes are requested.',
            ['materials/narrow-report.md'], 'advice_with_limits',
            'The supplied Unicode text has four code points but five display cells and folds at width4. An ellipsized width8 rendering no longer contains the complete identifier, and record/export retains those rendered segments rather than recovering original data. Keep canonical structured identifiers separately; choose width/wrapping deliberately and do not infer display width from len or promise exports undo cropping.', ['display_width_differs_from_character_count', 'recorded_rendering_does_not_restore_cropped_identifier']),
        ('RH-U02', 'understand', '解释局部capture和record缓冲的不同用途',
            'Trace the complete capture experiment, including destination output and the later export attempt. Explain which value to use for a local assertion and what record=False does. Do not modify files.',
            ['materials/capture.md'], 'explained',
            'capture.get returns captured newline and the destination StringIO remains empty. capture does not enable recording; export_text requires record=True and rejects this attempt. Use captured text for that local assertion, and deliberately enable/own a record buffer for later artifact exports.', ['capture_returns_local_output_without_enabling_record']),
        ('RH-D01', 'diagnose', '先取导出顺序和clear参数再定位缺失内容',
            'Investigate the supplied missing-HTML-content symptom. Request Console settings and the exact render/export order and clear arguments before attributing a cause. Diagnose disclosed facts only or close with an evidence plan if unavailable. No file changes are authorized.',
            ['materials/artifact-symptom.md'], 'diagnosed_no_code_change',
            'Initially request enough construction/record, render and export/clear evidence; visible terminal output alone does not establish export buffer state. Explain only the disclosed reproduction and existing compatible remedy, or accept insufficient_information. Do not assume a hidden first export or that empty content means the HTML string itself is empty.', None),
        ('RH-P01', 'plan', '规划一次渲染供多个制品共享的缓冲生命周期',
            'Plan the complete text-plus-HTML requirement using current record/export APIs. Define when to retain and clear, escaping and rendering limits, and normal/negative controls. Do not implement an exporter or write files.',
            ['materials/multiple-artifacts.md'], 'planned_without_library_change',
            'Enable record=True and use clear=False for each export that must leave content for later exports, then deliberately clear at the chosen ownership boundary. Default export_text clears; a following HTML export then lacks that content. HTML escapes literal angle brackets. Test both artifact contents and final empty state; capture is separate and rendered cropping is not reversible.', ['default_text_export_clears_later_artifact_content', 'multiple_exports_can_share_an_explicit_record_lifetime']),
        ('RH-P02', 'plan', '规划有明确字段政策的外发异常摘要',
            'Plan the supplied support-diagnostic requirement with existing traceback capabilities. Explain what show_locals=False proves, what still appears and which application-owned filtering/tests are needed. Do not read real logs, send messages, change files or claim a sanitizer has run.',
            ['materials/diagnostic-policy.md'], 'planned_without_library_change',
            'The synthetic exception message still appears with show_locals=False. That setting avoids deliberate locals display but does not redact exception messages, paths or code context. Define application-owned allowed fields/redaction or an explicit safe summary, preserve useful type/context and test markers across message/locals/path sources. Do not equate truncation, frame suppression or hidden locals with complete secret removal.', ['hiding_locals_does_not_redact_exception_message'])]
    scenes = [('RH-S01', '客户字段与终端样式', '按字段和输出目的地明确格式解释', ['RH-C01', 'RH-U01']),
        ('RH-S02', '窄屏报表与原始标识', '区分显示宽度、裁剪产物和规范数据', ['RH-C02']),
        ('RH-S03', '捕获、取证与多制品导出', '明确局部捕获和共享记录生命周期', ['RH-U02', 'RH-D01', 'RH-P01']),
        ('RH-S04', '支持诊断摘要', '保留有用错误信息并定义外发字段政策', ['RH-P02'])]
    build_project('rich', {'title': 'Rich终端报表工作场景', 'category': '终端展示与诊断',
        'description': '固定源码上的字面字段、纯文本、Unicode布局、捕获取证、多制品生命周期和异常摘要七项独立只读任务。'}, definitions, scenes, materials,
        branches={'RH-D01': [{'id': 'export-sequence', 'when': 'Console settings, render/export sequence and clear arguments have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/exports.md']}]},
        extra_entries={'RH-S03': [{'id': 'diagnose_only', 'task_ids': ['RH-D01']},
            {'id': 'unavailable', 'task_ids': ['RH-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
