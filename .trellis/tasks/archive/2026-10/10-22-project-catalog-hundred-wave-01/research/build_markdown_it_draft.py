"""制作真实编辑器预览、规则激活、定制渲染和引用元数据场景。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项任务，所有已有扩展能力按已有能力呈现。@return None。"""
    reproduction = '''from markdown_it import MarkdownIt

parser = MarkdownIt("commonmark", {"linkify": True})
print(parser.get_active_rules()["core"])
print(parser.render("Visit https://example.org/shop."))
parser.enable("linkify")
print(parser.render("Visit https://example.org/shop."))
'''
    materials = {
        'materials/editor.md': '# Orders\n\nTea **hot**\n',
        'materials/editor-policy.md': 'Parse the supplied three-line document with MarkdownIt(). Inspect opening/inline/closing tokens, nesting, inline.children, and actual map values. An editor wants to map rendered selections back to original source. Distinguish line ranges from a complete character/byte-offset map; no parser change or implementation is authorized.\n',
        'materials/url-symptom.md': 'A preview service says linkify was enabled but a plain URL remained unlinked. The actual preset/options, active rule chains, linkify dependency and complete input/output have not been supplied. Request evidence before assigning a cause.\n',
        'disclosure/linkify.py': reproduction,
        'disclosure/linkify-events.md': 'The complete synthetic reproduction runs with the frozen linkify-it-py dependency available. Its initial commonmark core chain does not include linkify; setting the option alone leaves the URL as text. Explicit enable("linkify") causes the supplied URL to become a link. No URL is fetched.\n',
        'disclosure/unavailable.md': 'The actual preset/options, active rules, dependency state and complete input/output cannot be supplied. No equivalent preview reproduction is available.\n',
        'materials/linkify.py': reproduction,
        'materials/linkify-policy.md': 'Use the full supplied commonmark reproduction with linkify-it-py present. The desired preview links the supplied explicit HTTPS URL. Compare the linkify option with the active core rule and existing enable API; do not fetch the URL, patch the core or add an imaginary always-on guarantee.\n',
        'materials/render-policy.md': 'For [Tea](https://example.org/orders), a custom link opener should retain the real href/label, add target=_blank, rel="noopener noreferrer" and data-origin containing the inert literal demo" <preview>. Compare registering callback name business-link-style with actual token type link_open. Use the current callback signature (renderer,tokens,index,options,env), Token.attrSet and renderer.renderToken. No project files may be edited and no HTML is executed.\n',
        'materials/references.md': '[a]: https://example.org/first\n\n[a]: https://example.org/second\n',
        'materials/reference-events.md': 'Call parser.parse on the supplied definitions with an explicit empty env dict; inspect tokens, env.references and env.duplicate_refs including source maps. Then render [a] using that same env and compare rendering [a] with a fresh empty dict. These represent separate documents for the isolation question. All URLs are inert strings and are not fetched.\n'}
    definitions = [
        ('IT-U01', 'understand', '解释块token和行内子项及行区间',
            'Trace tokens for the supplied editor document. Explain opening/inline/closing nesting, where strong markup appears, and actual heading/paragraph map ranges. Distinguish tokens from a ready-made per-character AST. Do not edit files.',
            ['materials/editor.md', 'materials/editor-policy.md'], 'explained',
            'The heading has opening/inline/closing tokens with nesting1/0/-1, and strong open/close are children of the paragraph inline token. Heading map is [0,1], paragraph/inline map [2,3], with half-open line ranges. Inline child maps are not full character-offset ranges; do not invent byte/column offsets.', ['block_and_inline_token_layers_are_distinct', 'source_maps_are_line_ranges']),
        ('IT-C01', 'consult', '界定编辑器选区定位的已有映射能力',
            'Advise how far the supplied existing Token.map metadata supports editor source positioning and what an application must define for exact rendered-selection mapping. Address lines versus characters/bytes without inventing a field or implementing a parser feature.',
            ['materials/editor.md', 'materials/editor-policy.md'], 'advice_with_limits',
            'Use existing half-open line ranges for block-level positioning; child tokens and transformations do not supply complete original character/byte offsets. Define document revision, normalization, Unicode indexing and desired selection granularity before proposing an exact mapping layer. Do not claim arbitrary HTML can be losslessly reversed or a nonexistent offset field already solves it.', ['source_maps_are_line_ranges']),
        ('IT-D01', 'diagnose', '先取预设和激活规则再判断URL未链接',
            'Investigate the supplied URL-preview symptom. Request actual preset/options, active rules, dependency availability and full input/output or a sufficient reproduction before attributing a cause. Diagnose consumed evidence only; unavailable evidence can legitimately limit the result. Do not edit files.',
            ['materials/url-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual parser construction, rule/dependency state and reproduction without assuming which condition failed. Relate only disclosed evidence to the pinned APIs and support the diagnosis and compatible remedy. Unavailable material permits insufficient_information and an evidence plan, rather than an invented parser defect.', None),
        ('IT-C02', 'consult', '用已有规则激活满足明确URL预览需求',
            'Explain the complete supplied commonmark/linkify reproduction with its dependency present. Identify why the first and second outputs differ and choose an existing compatible setup for this requirement. Do not modify the core or fetch any URL.',
            ['materials/linkify.py', 'materials/linkify-policy.md'], 'advice_no_code_change',
            'The linkify option and enabled rule are separate conditions. commonmark initially excludes the core linkify rule even with the option True. Existing enable("linkify") activates it and produces the supplied HTTPS link when linkify-it-py is available. Do not claim the option alone activates every rule or that a patch is necessary.', ['linkify_option_alone_does_not_activate_rule', 'existing_enable_activates_linkification']),
        ('IT-U02', 'understand', '解释渲染回调名称为何必须匹配实际token',
            'Compare registering the supplied custom opener under business-link-style versus link_open. Explain which callback runs, how its arguments bind, and why an arbitrary registration label need not raise an immediate error. Do not edit files.',
            ['materials/render-policy.md'], 'explained',
            'The renderer dispatches by actual Token.type. business-link-style is registered but unused because that token type is not produced; link_open runs once for this link. add_render_rule binds the renderer as the callback first argument. Do not invent a separate arbitrary business-label routing stage.', ['render_callback_requires_real_token_type']),
        ('IT-P01', 'plan', '规划保留链接与属性编码的已有渲染定制',
            'Plan the supplied link customization with current extension APIs. Keep the original destination/label, add the required attributes including the quote/angle-containing inert value, and preserve attribute encoding. No parser-core or project-file changes are authorized.',
            ['materials/render-policy.md'], 'planned_without_core_change',
            'Register a real link_open callback, use Token.attrSet to add target/rel/data-origin while retaining href, and delegate to renderer.renderToken for established attribute encoding. Preserve Tea and its destination, encode the quote/angle literal as attribute data, and verify callback execution with actual token types. Do not manually interpolate unencoded attributes or require a new core feature.', ['render_callback_requires_real_token_type', 'existing_render_token_preserves_link_and_encodes_attrs']),
        ('IT-U03', 'understand', '解释引用首定义和重复元数据',
            'Trace parsing of the supplied duplicate reference definitions with an explicit env. Explain the returned tokens, normalized label, retained href/map and duplicate_refs entry. Does the later definition silently replace the first? Do not edit files.',
            ['materials/references.md', 'materials/reference-events.md'], 'explained',
            'Definitions alone return no body tokens. env.references stores normalized label A with the first href and map[0,1]; duplicate_refs records the later second href/label A/map[2,3]. The later definition does not silently win, and env is the supplied mutable mapping.', ['first_reference_and_duplicate_metadata_preserved']),
        ('IT-C03', 'consult', '按文档边界管理调用方引用env',
            'Explain rendering [a] with the populated shared env versus a fresh empty dict in the supplied separate-document experiment. Recommend an explicit per-document metadata boundary using current APIs. Do not edit files.',
            ['materials/references.md', 'materials/reference-events.md'], 'advice_no_code_change',
            'The reused env intentionally supplies the first reference and creates that link, while a fresh empty env leaves [a] unresolved as literal text. Create or deliberately scope an env per independent document and retain it only for that parse/render operation. Do not claim the parser automatically clears caller metadata or that all shared env usage is a defect.', ['caller_owned_reference_env_is_reused'])]
    scenes = [('IT-S01', '编辑器token与定位', '明确现有行映射和精确选区需求的边界', ['IT-U01', 'IT-C01']),
        ('IT-S02', 'URL预览规则取证', '按真实预设、选项和规则选择已有解决方式', ['IT-D01', 'IT-C02']),
        ('IT-S03', '定制链接渲染', '用真实token类型和已有属性编码实现需求', ['IT-U02', 'IT-P01']),
        ('IT-S04', '引用定义和文档元数据', '区分首定义、重复信息和显式env共享', ['IT-U03', 'IT-C03'])]
    build_project('markdown-it-py', {'title': 'Markdown-it-py编辑预览工作场景', 'category': '结构化文档与预览',
        'description': '固定真实源码上的token、规则取证、渲染扩展和引用元数据八项独立只读任务。'},
        definitions, scenes, materials,
        branches={'IT-D01': [{'id': 'preview-evidence', 'when': 'The actual preset/options, active rules, dependency state and complete input/output have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/linkify.py', 'disclosure/linkify-events.md']}]},
        extra_entries={'IT-S02': [{'id': 'diagnose_only', 'task_ids': ['IT-D01']},
            {'id': 'unavailable', 'task_ids': ['IT-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
