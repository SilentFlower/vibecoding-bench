"""制作HTML内容迁移中实际存在的转换策略与诊断任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六个分别验收的转换任务。@return None。"""
    materials = {
        'materials/tag-policy.md': 'Convert <p>Hello <strong>paid <em>today</em></strong></p> with strip=["strong"]. Separately compare default conversion of <script>window.secret=7</script> with strip=["script"]. Explain what strip actually removes and what remains. A document migration must deliberately own whether an element and its content are omitted. Do not edit or describe strip as subtree removal.\n',
        'materials/table-header.md': 'Convert exactly <table><tr><td>tea</td><td>3</td></tr><tr><td>book</td><td>8</td></tr></table> under default options and table_infer_header=True. The supplier says both rows are products,not a header. Explain the actual Markdown rows and advise an appropriate header policy. No edits.\n',
        'materials/inline-images.md': 'Using heading_style="ATX",convert <h2><img src="chart.png" alt="Revenue"></h2> with defaults and keep_inline_images_in=["h2"]. Compare the paragraph control <p><img src="chart.png" alt="Revenue"></p>. Advise preserving a migration image where required without claiming image downloads or asset-copying happen automatically. No edits.\n',
        'materials/pre-language.md': 'The exact HTML is <pre class="language-python"> followed by newline,two spaces,print(1),two newlines,and </pre>. Compare code_language="text" with a callback returning None,then with a callback returning element["class"][0][9:]. Compare the default strip_pre with strip_pre=None. Explain fallback language,indentation and boundary-newline preservation. No implementation.\n',
        'materials/export-parity.md': 'The HTML file contains only <a href="https://example.test">https://example.test</a>. Compare markdownify(html),main([file]),and main(["--autolinks","--default-title",file]) from markdownify.main. Plan reproducible library/CLI exports by tracing the actual argparse defaults,flag actions and print newline. Preserve existing behavior;this task authorizes no CLI or library patch.\n',
        'disclosure/cache-reproduction.md': 'Complete reproduction: converter=MarkdownConverter();converter.convert("<strong>paid</strong>") returns **paid**. Then converter.options["strip"]=["strong"],and the same converter still returns **paid**. A fresh MarkdownConverter(strip=["strong"]) returns paid. The first conversion populated convert_fn_cache["strong"] with its bound conversion method;changing the options dict does not invalidate that cache. No other process or parser participates.\n',
        'disclosure/unavailable.md': 'The complete converter construction,reuse sequence,option values and clean fresh-instance control cannot be supplied.\n'}
    definitions = [
        ('MD-U01', 'understand', '区分移除标签格式与移除内容', 'Explain every supplied tag-policy result from the pinned implementation. No edits.', ['materials/tag-policy.md'], 'explained',
            'Stripping strong preserves its child content and nested em conversion,producing Hello paid *today*. Default script conversion removes its text,but strip=[script] bypasses that converter and exposes window.secret=7. strip selects tag-conversion suppression,not subtree deletion;own content omission separately.', ['strip_removes_tag_conversion_and_preserves_children']),
        ('MD-U02', 'understand', '保留没有表头的商品首行', 'Explain both complete table conversions and their semantic difference. No edits.', ['materials/table-header.md'], 'explained',
            'Default output creates an empty two-cell header and preserves tea/3 and book/8 as data rows. table_infer_header=True puts tea/3 before the separator and therefore reclassifies it as the Markdown header. Given the explicit supplier contract,do not infer a header from its first product;use default or a separately justified supplied header.', ['header_inference_reclassifies_the_first_data_row']),
        ('MD-C01', 'consult', '选择标题中的图表保留策略', 'Advise the exact image-parent controls and asset responsibilities. No edits.', ['materials/inline-images.md'], 'advice_no_code_change',
            'The h2 control defaults to ## Revenue as alt text. keep_inline_images_in=[h2] gives ## ![Revenue](chart.png). The paragraph control already preserves the Markdown image. Choose parent-tag policy explicitly and plan asset availability separately;conversion does not download chart.png.', ['inline_image_policy_depends_on_parent_tag']),
        ('MD-C02', 'consult', '保持代码块语言与边界空白', 'Advise actual callback fallback and whitespace policy using all supplied controls. No implementation.', ['materials/pre-language.md'], 'advice_no_code_change',
            'A None callback falls back to configured text;the class callback chooses python. Default strip_pre removes boundary blank lines but preserves the two-space indentation. strip_pre=None retains the original boundary newlines plus fence framing newlines. Choose content-preservation policy explicitly;do not claim None callback clears the configured language.', ['code_language_callback_falls_back_and_whitespace_is_explicit']),
        ('MD-P01', 'plan', '规划命令行和库导出的可重复性', 'Plan exact export parity from the supplied library/CLI controls. No code change.', ['materials/export-parity.md'], 'planned_without_library_change',
            'Library defaults autolinks=True/default_title=False yield <https://example.test>. CLI defaults store_true autolinks=False/store_false default_title=True yield a full link with href title. Existing --autolinks --default-title aligns those two choices;the misleadingly named latter flag disables default_title. CLI print adds one final newline. Pin invocation,parser/options,source and newline normalization and test exact output before migrating;no API patch is authorized.', ['cli_defaults_and_print_newline_require_an_explicit_export_profile']),
        ('MD-D01', 'diagnose', '诊断复用转换器的配置不生效', 'A reused document converter appears to ignore an option change. Request its complete construction,conversion and option sequence plus a fresh-instance control before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Diagnose only from actually consumed converter/options/sequence evidence. Ask for missing complete controls;when provided,trace the relevant option lookup and cached conversion behavior in the pinned source and propose an explicit per-profile converter lifetime. Missing controls support insufficient_information. Do not invent a parser cause or patch source.', None)]
    scenes = [('MD-S01', '内容与表格语义', '保留真实内容角色', ['MD-U01', 'MD-U02']),
        ('MD-S02', '图表与代码块迁移', '明确资源及格式策略', ['MD-C01', 'MD-C02']),
        ('MD-S03', '可重复导出', '核命令和库的实际默认', ['MD-P01']),
        ('MD-S04', '配置生效诊断', '取得完整生命周期证据', ['MD-D01'])]
    build_project('markdownify', {'title': 'Markdownify文档迁移工作场景', 'category': '内容转换与导出合同',
        'description': '标签与表头语义、图表和代码块保留、导出一致性及配置诊断。'}, definitions, scenes, materials,
        branches={'MD-D01': [{'id': 'complete-cache-reproduction',
            'when': 'Complete converter construction,option changes,call order and a clean fresh-instance control have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/cache-reproduction.md']}]},
        extra_entries={'MD-S04': [{'id': 'unavailable', 'task_ids': ['MD-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
