"""制作订阅语义、日期、来源、内容边界及一项明确授权修复。"""
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结七项实际任务，链接属性只合计为一个工程目标。@return None。"""
    public_tests = Path(__file__).with_name('feedgen-public-tests.py').read_text()
    materials = {
        'materials/order.md': 'Create two FeedGenerator instances. Add first,second,third by add_entry().id(name) on one and add_entry(order="append").id(name) on the other. Inspect IDs returned by entry(). Explain actual order before choosing a document listing policy. No edits.\n',
        'materials/format-projection.md': 'On one valid FeedEntry with id/title/content/explicit aware updated,add alternate links https://example.test/a then /b,and enclosures /one(length3,audio/mpeg) then /two(length0,audio/ogg). Compare RSS link/enclosure with all Atom link href values. Explain the actual per-format multiplicity. This task does not assume the independent Atom attribute repair has been applied. No edits.\n',
        'materials/date-input.md': 'On a valid entry compare published(datetime(2026,10,22)),published("2026-10-22T09:00:00"),and published("2026-10-22T09:00:00+02:00"). Inspect exact rejection and accepted Atom value/RSS pubDate. A supplier must state timezone meaning;do not silently attach the host zone. No edits.\n',
        'materials/source-update.md': 'On a valid entry,set source(url="https://example.test/old",title="Original"). Then separately inspect source(title="Edited") and source(url="https://example.test/new"),before a complete source(url="https://example.test/new",title="Edited"). Explain actual getter/setter behavior and resulting Atom source title/link. This API currently supports only title and URL,not arbitrary full Atom source metadata. No edits.\n',
        'materials/reproducible-build.md': 'Build two identical feeds with id urn:feed:1,title Documents,description Published documents,and an alternate https://example.test link. Explicitly set feed.updated,entry.updated and entry.published to datetime(2026,10,22,tzinfo=timezone.utc);use the same entry ID,title,text,order and export options. Compare actual atom_str and rss_str bytes. Plan reproducible exports without adding a clock API or changing published meaning. Constructors have current-time defaults if dates are omitted. No implementation.\n',
        'materials/link-repair.md': 'Repair the pinned FeedEntry.atom_entry serialization so each link keeps all supported nonempty string attributes rel,type,hreflang,title,length as well as href. Keep independent links in order,Unicode titles and length="0";omit absent/None/empty optional values,retain the link setter default alternate and preserve input dictionaries,RSS selection and feed-level behavior. The original overwrites its link dictionary with an XML Element. Authorization is only library/feedgen/entry.py and meaningful public regression tests at app/test_atom_link.py. Preserve all original tests,configuration and other features. No unrelated extension or network request is authorized.\n',
        'materials/public-test-example.py': public_tests,
        'disclosure/nontext-content.md': 'Complete isolated reproduction: a valid entry has id,title,aware updated and normal text content. Replace its content with content("AA==",type="application/octet-stream") and call atom_entry(). The exact exception is NotImplementedError: base64 encoded content is not supported at the moment. Pull requests adding support are welcome. A separate otherwise-identical entry calls content(src="https://example.test/blob");its Atom content element has src=https://example.test/blob. Neither control fetches that URL or establishes availability.\n',
        'disclosure/unavailable.md': 'The exact content setter values/type,export call,exception and a complete valid-entry control cannot be supplied.\n'}
    definitions = [
        ('FG-U01', 'understand', '解释导入文档的条目顺序', 'Explain both complete entry-order controls. No edits.', ['materials/order.md'], 'explained',
            'Default add_entry prepends,so the first feed is third,second,first. Explicit append gives first,second,third. Choose the existing insertion order required by the document list;neither order implies sorting by publication time.', ['default_prepend_and_explicit_append_have_different_document_order']),
        ('FG-U02', 'understand', '区分RSS和Atom的链接投影', 'Explain the complete per-format link and enclosure controls. No edits.', ['materials/format-projection.md'], 'explained',
            'RSS selects the last alternate b and last enclosure two with length0/audio/ogg. Atom retains all four href values in insertion order. Formats have different multiplicity;do not claim all RSS attachments survive or assume the separately authorized Atom attribute repair is present.', ['rss_projects_last_alternate_and_enclosure_while_atom_keeps_all_links']),
        ('FG-C01', 'consult', '明确订阅日期的时区来源', 'Advise date input using all actual failure/success controls. No implementation.', ['materials/date-input.md'], 'advice_no_code_change',
            'Both naive datetime and offset-free string raise ValueError Datetime object has no timezone info. The aware string preserves09:00+02:00 and RSS emits Thu,22 Oct2026 09:00:00 +0200. Obtain source timezone meaning explicitly rather than guess the host zone;this API validates awareness instead of inferring it.', ['dates_require_explicit_timezone_instead_of_guessing_source_zone']),
        ('FG-C02', 'consult', '避免来源信息的部分更新被忽略', 'Advise exact source getter/setter behavior and the supported metadata scope. No edits.', ['materials/source-update.md'], 'advice_no_code_change',
            'Both partial calls leave the original URL/title unchanged because source only writes when both are supplied. The complete call changes Atom title to Edited and link href to new. Reapply the full intended pair and retain any other provenance separately;the current API does not expose full Atom source fields or merge arbitrary partial metadata.', ['source_metadata_updates_require_both_url_and_title']),
        ('FG-P01', 'plan', '规划可复现的订阅归档构建', 'Plan reproducible local RSS/Atom artifacts from the complete controls. No implementation.', ['materials/reproducible-build.md'], 'planned_without_library_change',
            'With all supplied feed/entry dates,contents,order and options explicit,both actual Atom and RSS byte pairs match. feed.updated also sets RSS lastBuildDate,while entry published controls pubDate. Constructors otherwise use current time. Pin those inputs and source/dependencies/export policy,retain source time provenance and compare artifacts;do not overwrite historical publication dates or claim a new clock API.', ['explicit_feed_and_entry_dates_make_the_supplied_build_reproducible']),
        ('FG-D01', 'diagnose', '先核内容类型再解释导出失败', 'A document entry fails during Atom export after changing its content. Request exact content/type/export calls,the exception and a complete valid-entry control before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually supplied content/type/export and exception evidence. Request missing controls,trace the specific supported-content branch when complete,and distinguish an existing alternative from a proposed feature. Missing evidence supports insufficient_information. No source change or remote fetch is authorized.', None),
        ('FG-M01', 'modify', '修复Atom条目链接元数据丢失', 'Implement the narrowly authorized link metadata repair and meaningful public regressions. Preserve all original controls and run the full applicable original regression.', ['materials/link-repair.md', 'materials/public-test-example.py'], 'implemented_with_public_regression_tests',
            'Repair the actual dictionary/Element shadowing root cause so all supported nonempty string link attributes,including Unicode and string zero length,survive independently and in order. Preserve missing/empty omission,input dictionaries,RSS projection and all other behavior. Only the authorized implementation and public test file may change;public tests must fail on original and pass after the repair.', ['atom_entry_preserves_all_supported_nonempty_link_attributes'])]
    scenes = [('FG-S01', '条目顺序与格式投影', '核清单与链接实际语义', ['FG-U01', 'FG-U02']),
        ('FG-S02', '输入与来源合同', '明确时区和完整来源对', ['FG-C01', 'FG-C02']),
        ('FG-S03', '可复现订阅归档', '固定真实输入与输出策略', ['FG-P01']),
        ('FG-S04', '内容导出诊断', '先取得完整内容和异常', ['FG-D01']),
        ('FG-S05', 'Atom链接修复', '保留单一根因下的全部元数据', ['FG-M01'])]
    build_project('feedgen', {'title': 'Feedgen文档订阅工作场景', 'category': 'RSS/Atom语义与序列化',
        'description': '顺序、格式投影、日期、来源、归档、内容诊断和链接修复七项任务。'}, definitions, scenes, materials,
        modifications={'FG-M01': ['library/feedgen/entry.py', 'app/test_atom_link.py']},
        branches={'FG-D01': [{'id': 'complete-content-reproduction',
            'when': 'Exact content/type/export calls,exception and complete valid-entry controls have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/nontext-content.md']}]},
        extra_entries={'FG-S04': [{'id': 'unavailable', 'task_ids': ['FG-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/license.bsd', 'seed/library/license.lgpl'])


if __name__ == '__main__':
    main()
