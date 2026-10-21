"""制作Docutils文档发布、引用取证、投稿控制、锚点和表格任务。"""
from draft_content import build_project


def main() -> None:
    """保存五场景八项独立只读任务及嵌套源码、混合许可路径。@return None。"""
    materials = {
        'materials/page.rst': 'Title\n=====\n\nCoffee 咖啡.\n',
        'materials/publishing.md': 'Compare publish_doctree of the supplied file with default title transforms and doctitle_xform=False. For HTML5, compare publish_parts fragment with publish_string output_encoding=utf-8 and unicode. The application embeds a content fragment in an existing page and owns the final HTTP encoding. Disable external configuration with _disable_config=True in every synthetic call. No files may be changed.\n',
        'materials/reference-symptom.md': 'A documentation build returned output even though a reference looked broken in the browser. The complete reStructuredText, source path, publish API and reporter/exit settings have not been supplied. Investigate before deciding why.\n',
        'disclosure/reference.md': 'Complete reproduction: publish_doctree("See missing_.\\n",source_path="guide.rst",settings_overrides={"_disable_config":True,"report_level":2,"halt_level":6,"warning_stream":a_StringIO}). No target named missing is defined. The programmatic function returns a document rather than enabling command-line exit-status handling.\n',
        'disclosure/unavailable.md': 'The original reStructuredText, invocation and reporter/exit configuration cannot be supplied. No complete reproduction is available.\n',
        'materials/build-gate.md': 'For the complete synthetic source See missing_. followed by newline, the build must reject ERROR-level unresolved targets. Compare report_level=5,halt_level=6 with halt_level=3. Use programmatic publishing, not an assumed CLI exit code. Preserve useful captured diagnostics and distinguish raising from visual message suppression. No implementation is requested.\n',
        'materials/directives.md': 'Compare a trusted synthetic raw HTML directive containing <b>trusted-marker</b> with raw_enabled=False. Separately create only a synthetic fragment.rst containing synthetic-include-marker, include it from a synthetic main.rst and compare file_insertion_enabled=False. These are permitted throwaway examples, never real files or accounts. State what each setting controls; no project changes are authorized.\n',
        'materials/submission-policy.md': 'A public documentation sidebar accepts untrusted reStructuredText. Raw HTML and file/url inclusion directives must be disabled. Ordinary approved https links and CSV tables are still needed. Plan explicit settings, source/config isolation, link/HTML output policy and bounded rendering; distinguish directive switches from a universal filesystem/network sandbox or complete sanitization. Do not deploy, fetch URLs or implement a renderer.\n',
        'materials/anchors.md': 'Render two separate documents using the explicit target .. _payments-api: before a top heading: first Payment methods, then Payment endpoints. Compare all node IDs and title-derived IDs. Published external links must keep the agreed payments-api anchor despite renaming the visible heading. No files may be changed.\n',
        'materials/stock.rst': '.. csv-table:: Stock\n   :header: "item", "qty"\n\n   "tea, green", 2\n   "咖啡", 3\n'}
    definitions = [
        ('DU-U01', 'understand', '解释首节标题为何进入文档标题',
            'Trace the supplied document tree with default transforms and doctitle_xform=False. Explain the resulting title/section structure and whether the source was lost. Do not edit files.',
            ['materials/page.rst', 'materials/publishing.md'], 'explained',
            'The lone first top-level section is promoted to the document title by default, so no section node remains for that heading. Disabling doctitle_xform retains a section and its title. This is a configured transform, not missing text or a parser corruption.', ['first_section_can_be_promoted_to_document_title']),
        ('DU-C01', 'consult', '选择网页片段和最终编码的责任边界',
            'Recommend existing publishing APIs for the supplied embedded-page requirement. Compare actual fragment/whole-document and bytes/str results, including original Unicode. Do not implement or double-wrap/double-encode content.',
            ['materials/page.rst', 'materials/publishing.md'], 'advice_no_code_change',
            'publish_parts returns text parts; choose the intended fragment rather than a full HTML document. publish_string with utf-8 returns bytes, while output_encoding=unicode returns str. Preserve Unicode and let the outer page/HTTP boundary encode once; rendered parts and text are not interchangeable with already encoded bytes.', ['parts_and_string_have_explicit_output_ownership']),
        ('DU-D01', 'diagnose', '先取文档与发布设置再定位失效引用',
            'Investigate the supplied broken-reference symptom. Request the complete relevant reStructuredText, publish invocation/source path and reporter/exit settings. Diagnose only disclosed evidence or finish with an evidence plan if unavailable. No file changes are authorized.',
            ['materials/reference-symptom.md'], 'diagnosed_no_code_change',
            'The initial browser symptom cannot establish reference syntax, missing targets or failure policy. Request sufficient actual source and publishing settings, then explain only the disclosed messages/return behavior. insufficient_information is valid if unavailable; do not assume the hidden source or confuse a returned output with absence of diagnostics.', None),
        ('DU-C02', 'consult', '区分诊断输出阈值和构建失败阈值',
            'Meet the supplied ERROR-rejection build policy with existing programmatic APIs. Explain both complete threshold controls, captured evidence and actual exception behavior. Do not implement or invent a CLI status for a programmatic call.',
            ['materials/build-gate.md'], 'advice_no_code_change',
            'The unresolved target generates an ERROR/system_message level3 and problematic reference. report_level5 changes report visibility but halt_level6 still permits return. halt_level3 raises SystemMessage at this error. Set explicit halt and catch/report at the application boundary, or deliberately use the documented CLI exit policy; report suppression alone is not a failing build gate.', ['unresolved_reference_is_reported_without_default_programmatic_failure', 'halt_level_controls_failure_even_when_report_level_differs']),
        ('DU-C03', 'consult', '限定raw与include开关各自保证的行为',
            'Explain the complete permitted synthetic directive comparisons using current settings. Give allowed and blocked controls, diagnostic behavior and the limits of the guarantee. Do not inspect real external files or modify the project.',
            ['materials/directives.md'], 'advice_with_limits',
            'Trusted raw produces a raw node; raw_enabled=False rejects that directive. A normal synthetic include reads its fragment, while file_insertion_enabled=False prevents that include and emits a disabled-directive warning. Disable both for the stated restriction; neither switch alone establishes a full OS sandbox, arbitrary plugin safety or output sanitization.', ['raw_and_include_are_separately_controlled']),
        ('DU-P01', 'plan', '规划投稿文档的指令和展示策略',
            'Plan the supplied public-sidebar acceptance policy using the existing publisher. Keep approved ordinary links/tables useful, identify what switches prove and what the application must decide, and propose normal/negative controls. No implementation, deployment or URL access is authorized.',
            ['materials/submission-policy.md', 'materials/directives.md'], 'planned_without_library_change',
            'Explicitly disable raw_enabled and file_insertion_enabled, isolate source paths/external configs and restrict parser/plugin/config ownership. Ordinary external reference links still survive, so apply an explicit approved link/rendered-output policy rather than claiming both switches sanitize all HTML/URLs. Define bounded rendering and rejection/diagnostic handling with raw/include negative and approved-link/table positive controls. Do not claim a sandbox or sanitizer was executed.', ['raw_and_include_are_separately_controlled', 'directive_settings_do_not_remove_normal_external_links']),
        ('DU-U02', 'understand', '用显式目标保持改名后的外部锚点',
            'Trace both complete heading/explicit-target examples and compare actual node IDs. Explain which agreed external anchor survives and which automatic ID changes. Do not edit documents or promise every generated ID is stable.',
            ['materials/anchors.md'], 'explained',
            'payments-api remains a target in both trees; payment-methods changes to payment-endpoints with the visible title. Use the explicit agreed target for stable external links, preserve uniqueness, and do not mistake title-derived automatic IDs for an immutable routing contract.', ['explicit_targets_survive_title_rename']),
        ('DU-U03', 'understand', '核对CSV指令的真实单元格和Unicode内容',
            'Trace the supplied complete csv-table document into table/row/entry nodes. Count header/data rows and identify the exact comma-containing and Unicode cell values. Do not split the CSV naively or modify files.',
            ['materials/stock.rst'], 'explained',
            'The result is one table with three rows including the header, each with two cells. Quoted tea, green stays one cell, quantities are textual table entries2/3, and the original Unicode item survives. This directive parses CSV data rather than turning every comma into a table boundary.', ['csv_table_keeps_quoted_cells_and_unicode'])]
    scenes = [('DU-S01', '文档树与网页片段', '明确标题转换、整页和片段的输出责任', ['DU-U01', 'DU-C01']),
        ('DU-S02', '引用取证与构建门禁', '根据真实文档和阈值决定失败策略', ['DU-D01', 'DU-C02']),
        ('DU-S03', '投稿指令与展示政策', '限制文件插入和raw并明确应用层责任', ['DU-C03', 'DU-P01']),
        ('DU-S04', '公开文档稳定锚点', '区分显式目标和随标题变化的自动ID', ['DU-U02']),
        ('DU-S05', '结构化库存表格', '保留引用逗号字段和Unicode表格内容', ['DU-U03'])]
    build_project('docutils', {'title': 'Docutils文档发布工作场景', 'category': '文档解析与发布',
        'description': '固定完整源码上的文档树、引用取证、失败阈值、投稿设置、稳定锚点和库存表格八项独立只读任务。'},
        definitions, scenes, materials, python_paths=['library/docutils', 'app'],
        license_files=['seed/library/docutils/COPYING.rst', 'seed/library/docutils/licenses/BSD-0-Clause.rst',
            'seed/library/docutils/licenses/BSD-2-Clause.rst', 'seed/library/docutils/licenses/gpl-3-0.txt'],
        branches={'DU-D01': [{'id': 'publish-evidence', 'when': 'The original source, publish invocation and reporter/exit settings have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/reference.md']}]},
        extra_entries={'DU-S02': [{'id': 'diagnose_only', 'task_ids': ['DU-D01']},
            {'id': 'unavailable', 'task_ids': ['DU-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
