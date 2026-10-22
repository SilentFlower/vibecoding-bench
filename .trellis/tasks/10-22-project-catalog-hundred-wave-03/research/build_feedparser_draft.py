"""制作解析质量、日期与跨格式归档的真实任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项独立只读任务。@return None。"""
    materials = {
        'materials/recovery.md': 'Parse local BytesIO containing <rss version="2.0"><channel><title>News</title><item><title>One</title><description>A & B</description></item></channel></rss>,and separately an empty BytesIO. Inspect bozo,exception and recovered entries. Explain what syntax recovery and empty success do and do not establish for business acceptance. No edits.\n',
        'materials/date-fields.md': 'Parse local RSS bytes whose one item has pubDate Thu, 22 Oct 2026 09:00:00 +0200. Inspect published,published_parsed[:6],"updated" in item,dict.__contains__(item,"updated"),then explicitly access item.updated while recording its warning. Explain UTC tuple conversion and compatibility lookup versus actual stored key. No edits.\n',
        'materials/html-policy.md': 'The RSS description contains CDATA <script>alert(1)</script><b>Visible</b>. Compare default parse and sanitize_html=False using explicit local streams. Explain actual summary text and advise downstream rendering policy and source preservation. Do not claim general browser/application safety from this single conversion or change global parser defaults. No implementation.\n',
        'materials/relative-content.md': 'A local Atom feed has one entry with content type=html containing the escaped markup <a href="doc">One</a>. Parse BytesIO with response_headers={"content-location":"https://example.test/base/"};compare default and resolve_relative_uris=False. Advise source/base provenance for archived HTML links;resolving a string does not download its target. No edits.\n',
        'materials/normalization-plan.md': 'Parse JSON Feed1 from local bytes with one item id=one,content_text=Text,tags=[tag],and one attachment URL=https://example.test/a,mime_type=audio/ogg,size_in_bytes=12. Inspect dict.__getitem__ for raw content/category/enclosures,then ordinary item.tags,item.category and item.enclosures. Plan explicit per-format normalization and provenance before a unified archive assumes RSS-style structures. Preserve raw evidence and report unsupported/missing fields rather than inventing them. No implementation.\n',
        'disclosure/modified-date.md': 'Complete local JSON Feed1 input has title News and one item{id:one,content_text:Text,date_modified:2026-10-22T09:00:00+02:00};no date_published or date_updated is supplied. Parse uses explicit BytesIO and content-type application/feed+json. Actual bozo isFalse and an entry is returned,but dict.__contains__(entry,"updated") isFalse. JSONParser.parse_entry checks for date_updated before reading date_modified. Thus the supplied standard modified field never reaches that branch;no network or caller mutation occurs. No source repair is authorized by this diagnosis.\n',
        'disclosure/unavailable.md': 'The complete feed bytes,content type,parse calls,raw key inspection and accessors cannot be supplied.\n'}
    definitions = [
        ('FP-U01', 'understand', '区分容错解析和业务可用性', 'Explain every supplied malformed/empty input control. No edits.', ['materials/recovery.md'], 'explained',
            'The unescaped ampersand makes malformed RSS bozoTrue,but recovery still returns itemOne. Empty input has bozoFalse and no entries. Neither bozo alone nor nonempty entries proves required business completeness;retain exception evidence and apply explicit acceptance policy.', ['bozo_status_and_recovered_entries_require_separate_acceptance']),
        ('FP-U02', 'understand', '核真实日期字段和历史兼容访问', 'Explain UTC parsed values,stored-key checks and warning lookup. No edits.', ['materials/date-fields.md'], 'explained',
            'The09:00+02 date becomes UTC tuple2026,10,22,7,0,0. updated is not actually stored and both membership checks areFalse,but its compatibility accessor falls back to published and emits DeprecationWarning. Do not invent a separate modification timestamp from that legacy lookup.', ['parsed_dates_are_utc_and_legacy_updated_fallback_is_not_a_real_key']),
        ('FP-C01', 'consult', '选择HTML内容归档和呈现策略', 'Advise actual summary conversion and downstream responsibility. No implementation.', ['materials/html-policy.md'], 'advice_no_code_change',
            'Default summary retains<b>Visible</b> and removes the supplied script and body;disabled sanitization retains script markup. Decide how to preserve source and render content downstream,keep explicit per-call settings,and do not infer universal browser/application safety or authorize disabling protection globally.', ['html_sanitization_changes_markup_and_requires_a_downstream_rendering_policy']),
        ('FP-C02', 'consult', '保留本地订阅的相对资源基准', 'Advise both local-content URI controls and provenance. No edits.', ['materials/relative-content.md'], 'advice_no_code_change',
            'With supplied content-location,the default HTML link resolves to https://example.test/base/doc;resolve_relative_urisFalse retains href=doc. Record the original source/base and chosen rewrite policy. This is string resolution,not remote retrieval or proof of resource availability.', ['relative_html_uris_need_explicit_local_source_provenance']),
        ('FP-P01', 'plan', '规划跨格式订阅字段规范化', 'Plan normalization using actual raw storage and accessor controls. No implementation.', ['materials/normalization-plan.md'], 'planned_without_library_change',
            'This pinned JSON parser stores content as a dict,raw category as[tag],and raw enclosures directly. Ordinary tags/category lookups require tags and fail;enclosures requires links and fails despite that raw stored field. Inspect actual per-format structures,normalize content/tags/attachments explicitly into an owned archive schema,retain raw provenance and failures,and test equivalent RSS/Atom/JSON controls. A uniform parser return wrapper alone does not establish identical field shapes.', ['json_feed_raw_storage_and_legacy_accessors_need_an_explicit_normalization_layer']),
        ('FP-D01', 'diagnose', '诊断订阅修改日期缺失', 'An archived JSON item appears to lose its modification date. Request complete source bytes,content type,calls,raw keys and accessors before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually supplied source/date/parse and raw-key evidence. Request missing controls;when complete,trace the exact date mapping and distinguish real fields from compatibility accessors or unsupported mapping. Missing evidence supports insufficient_information. No patch,remote fetch or guessed date is authorized.', None)]
    scenes = [('FP-S01', '解析结果与日期事实', '分清容错和真实字段', ['FP-U01', 'FP-U02']),
        ('FP-S02', 'HTML归档策略', '明确呈现与相对基准', ['FP-C01', 'FP-C02']),
        ('FP-S03', '跨格式规范化', '保留原始结构与来源', ['FP-P01']),
        ('FP-S04', '日期映射诊断', '核完整输入和访问方式', ['FP-D01'])]
    build_project('feedparser', {'title': 'Feedparser本地订阅验收工作场景', 'category': '容错、字段与内容归档',
        'description': '容错验收、日期事实、HTML处理、相对资源、跨格式方案和日期诊断。'}, definitions, scenes, materials,
        branches={'FP-D01': [{'id': 'complete-json-date',
            'when': 'Complete feed bytes,content type,calls,raw key inspections and accessors have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/modified-date.md']}]},
        extra_entries={'FP-S04': [{'id': 'unavailable', 'task_ids': ['FP-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
