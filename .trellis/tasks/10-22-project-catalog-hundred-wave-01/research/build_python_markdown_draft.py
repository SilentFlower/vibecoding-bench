"""制作真实文档发布、状态隔离、目录和扩展选择场景。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项独立只读任务，保留HTML字面与上游API。@return None。"""
    reproduction = '''from markdown import Markdown
from markdown.extensions.footnotes import FootnoteExtension

renderer = Markdown(extensions=[FootnoteExtension()])
print(renderer.convert("Coffee[^a]\\n\\n[^a]: first-note"))
print(renderer.convert("Tea[^a]"))
renderer.reset()
print(renderer.convert("Tea[^a]"))
'''
    materials = {
        'materials/documents.py': reproduction,
        'materials/document-lifecycle.md': 'Compare reusing the same configured Markdown instance for these separate documents with calling reset between documents and creating separate instances. Explain which state belongs to a document and what the existing API requires; do not change files.\n',
        'materials/foreign-content-symptom.md': 'A publication service says one rendered article sometimes contains content associated with another article. The actual converter construction/reuse, extensions and input/output sequence have not been supplied. Request sufficient evidence before attributing a cause.\n',
        'disclosure/documents.py': reproduction,
        'disclosure/document-events.md': 'The synthetic reproduction reuses one renderer for two independent articles. The second output before reset contains first-note although its own input contains no footnote definition; after reset the same input retains a literal unresolved reference and no first-note. No concurrency or production cache facts are supplied.\n',
        'disclosure/unavailable.md': 'The actual converter lifecycle, extension configuration and full input/output sequence cannot be supplied. No equivalent incident reproduction is available.\n',
        'materials/raw-content.md': '<span data-origin="comment">coffee</span>\n',
        'materials/content-policy.md': 'The same application publishes trusted internal articles which may intentionally include raw HTML, and separate untrusted visitor comments whose arbitrary raw HTML must not be trusted. Inspect the supplied inert span and its code-span form. Explain current renderer output and propose a deliberate output policy per channel. Do not execute HTML, install tools or claim a sanitizer has been tested.\n',
        'materials/publication-plan.md': 'Plan the two supplied publishing channels, including source trust, enabled extension configuration, one-document state lifecycle, output treatment/allow policy and regression examples. The approved sanitizer and application publication policy are not provided; identify that boundary without inventing a built-in sanitization or safe-mode API. No files may be changed.\n',
        'materials/outline.md': '# Cafe\n\n## Menu\n\n## Menu\n\n### Hidden\n',
        'materials/outline-policy.md': 'Use an explicit TocExtension(toc_depth="1-2") instance, inspect HTML and Markdown.toc_tokens. Report hierarchy and generated duplicate ids. Separately use TocExtension(slugify=slugify_unicode) for # 咖啡 followed by two ## 菜单 headings. The application wants Chinese characters kept in anchors and understands article identity must be explicit when combining multiple documents.\n',
        'materials/table.md': '| Item | Qty |\n| --- | ---: |\n| Tea | 2 |\n',
        'materials/extensions-policy.md': 'Compare no extension, an explicit TableExtension instance, and the full module string markdown.extensions.tables. This is a source-only import environment with no installed Markdown distribution entry-point metadata; the short name tables fails to import. Also compare output_format="html" and "xhtml" for a horizontal rule. The application can choose current instance/full-module APIs and does not request a core-loader change or installation of another published Markdown copy.\n'}
    definitions = [
        ('PM-U01', 'understand', '解释多文档复用实例和reset边界',
            'Trace the supplied complete converter program. Explain why the second independent document differs before/after reset and how separate instances compare. Does convert automatically reset registered extension state between documents? Do not edit files.',
            ['materials/documents.py', 'materials/document-lifecycle.md'], 'explained',
            'convert does not automatically reset document state. The shared footnote extension retains the first definition, while reset clears registered extension/document state and the second unresolved reference remains literal without first-note. A separately configured fresh instance matches the reset independent document. Use existing reset or separate instances.', ['shared_instance_preserves_footnote_state', 'reset_separates_document_state', 'fresh_instance_matches_reset_document']),
        ('PM-D01', 'diagnose', '先取转换生命周期再判断文章内容串入',
            'Investigate the supplied foreign-content symptom. Request actual converter construction/reuse, extensions and full input/output sequence or an equivalent reproduction before assigning a cause. Diagnose disclosed evidence only and state the evidence limit if unavailable. Do not edit files.',
            ['materials/foreign-content-symptom.md'], 'diagnosed_no_code_change',
            'The symptom alone is insufficient. Obtain the real lifecycle, extension configuration and sequence; relate only consumed evidence to actual pinned APIs and support the resulting diagnosis and limits. Do not preassign cache, concurrency, parser or application causes. Unavailable evidence permits insufficient_information and a concrete reproduction plan.', None),
        ('PM-C01', 'consult', '区分原始HTML渲染和业务输出策略',
            'Explain the supplied inert raw span versus its code-span form and assess the two explicitly stated publishing policies. Does Markdown conversion itself sanitize arbitrary HTML? Recommend the appropriate application boundary without installing tools or editing files.',
            ['materials/raw-content.md', 'materials/content-policy.md'], 'advice_with_limits',
            'Raw inert HTML is intentionally preserved in ordinary conversion; a Markdown code span escapes the literal markup as code. The renderer does not itself sanitize arbitrary HTML. Trusted article policy may allow intentional markup, while visitor output needs an explicitly approved treatment/allow policy after conversion as appropriate; do not invent built-in safe mode or claim an unprovided sanitizer ran.', ['inert_raw_html_is_preserved', 'code_span_escapes_literal_markup']),
        ('PM-P01', 'plan', '规划两种发布渠道和独立文档生命周期',
            'Plan the supplied trusted-article and visitor-comment publishing channels using current renderer capabilities. Cover extension selection, document state isolation, explicit output policy and verification examples, while identifying the missing approved output-treatment choice. Do not implement changes.',
            ['materials/publication-plan.md', 'materials/content-policy.md', 'materials/document-lifecycle.md'], 'planned_with_explicit_boundaries',
            'Separate channel trust/policy explicitly, configure actual extensions, reset or isolate renderers per document, and apply the approved output policy before publication. Include multi-document and raw/code HTML regression examples and identify unprovided treatment decisions. Do not claim conversion sanitizes output, a safe-mode flag exists, or an external treatment has already been validated.', ['inert_raw_html_is_preserved', 'reset_separates_document_state']),
        ('PM-U02', 'understand', '解释文章目录层级、重复锚点和深度',
            'Trace the supplied outline with TocExtension(toc_depth="1-2"). Give actual nested toc_tokens ids for Cafe and the duplicate Menu headings. Explain whether excluding level3 from the TOC also removes its heading from body HTML. Do not edit files.',
            ['materials/outline.md', 'materials/outline-policy.md'], 'explained',
            'The single top token cafe has children menu and menu_1. toc_tokens preserves this hierarchy. Depth1-2 excludes Hidden from TOC tokens while body still contains its level3 heading/id; it does not delete content. Do not flatten tokens or assume duplicate ids are identical.', ['toc_tokens_keep_hierarchy_and_unique_ids', 'toc_depth_does_not_remove_body_heading']),
        ('PM-C02', 'consult', '用已有Unicode回调满足中文锚点策略',
            'Meet the supplied Chinese-anchor requirement with existing TocExtension configuration. Explain duplicate Chinese headings, current article uniqueness and what must remain an explicit application convention across combined documents. No changes are authorized.',
            ['materials/outline-policy.md'], 'advice_no_code_change',
            'Configure the existing slugify_unicode callback rather than modifying the default slugifier. The supplied tokens use 咖啡 with children 菜单 and 菜单_1. Generated uniqueness is scoped to a rendered document, so a combined publication still needs a stable article/anchor convention; no global cross-document id registry is provided.', ['existing_unicode_slugify_keeps_chinese']),
        ('PM-U03', 'understand', '解释显式表格扩展和序列化格式选择',
            'Compare the supplied table input with no extension and an explicit TableExtension instance. Then explain the horizontal-rule output under html versus xhtml formats. Distinguish these current choices from a requested parser change. Do not edit files.',
            ['materials/table.md', 'materials/extensions-policy.md'], 'explained',
            'Bare Markdown does not produce a table element for this table syntax; TableExtension does. Existing output_format=html yields <hr> while xhtml yields <hr /> for the rule. These are explicit extension/serializer choices, not evidence that the source needs a patch.', ['table_requires_explicit_extension', 'html_xhtml_empty_element_formats']),
        ('PM-C03', 'consult', '在仅源码环境用已有明确扩展入口',
            'Explain the supplied source-only extension-loading situation and select a current API that works without installed distribution entry-point metadata. Compare a short alias, full module string and an explicit extension instance. Do not alter the loader or install a different Markdown copy.',
            ['materials/table.md', 'materials/extensions-policy.md'], 'advice_no_code_change',
            'Short aliases depend on installed markdown.extensions entry points; an importable source checkout alone does not supply them. In the supplied environment tables falls through to a module import and fails. Existing full markdown.extensions.tables or a TableExtension instance loads the actual candidate and yields equivalent output. Do not claim a universal alias failure for properly installed distributions or install another implementation as a substitute.', ['source_only_full_module_and_instance_work'])]
    scenes = [('PM-S01', '独立文章转换会话', '区分文档状态与证据充分的内容串入诊断', ['PM-U01', 'PM-D01']),
        ('PM-S02', '文档与访客内容发布', '按明确业务信任边界规划渲染和输出策略', ['PM-C01', 'PM-P01']),
        ('PM-S03', '文章目录和中文锚点', '用现有目录层级与回调满足发布要求', ['PM-U02', 'PM-C02']),
        ('PM-S04', '扩展加载和输出格式', '在真实源码环境选择已有明确入口', ['PM-U03', 'PM-C03'])]
    build_project('python-markdown', {'title': 'Python-Markdown文档发布工作场景', 'category': '文档转换与发布',
        'description': '固定真实源码上的多文章取证、发布策略、中文目录和明确扩展入口八项独立只读任务。'},
        definitions, scenes, materials,
        branches={'PM-D01': [{'id': 'document-evidence', 'when': 'The actual converter lifecycle, extension configuration and complete input/output sequence have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/documents.py', 'disclosure/document-events.md']}]},
        extra_entries={'PM-S01': [{'id': 'diagnose_only', 'task_ids': ['PM-D01']},
            {'id': 'unavailable', 'task_ids': ['PM-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
