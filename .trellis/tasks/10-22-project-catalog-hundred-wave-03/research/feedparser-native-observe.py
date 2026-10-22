"""观察本地订阅流的异常、日期、HTML策略及JSON结构差异。"""
from io import BytesIO
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
import warnings

import feedparser


def parse_xml(text: str, **options):
    """明确以本地流解析合成XML。@param text XML。@param options 解析选项。@return 实际结果。"""
    return feedparser.parse(BytesIO(text.encode()), **options)


def main() -> None:
    """全部输入为本地流，URL仅为资源文字。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(feedparser.__file__).resolve() == root / 'library/feedparser/__init__.py'}
    task = argv[1]
    if task == 'FP-U01':
        malformed = parse_xml('<rss version="2.0"><channel><title>News</title><item><title>One</title><description>A & B</description></item></channel></rss>')
        empty = feedparser.parse(BytesIO(b''))
        result['bozo_status_and_recovered_entries_require_separate_acceptance'] = (
            bool(malformed.bozo) and len(malformed.entries) == 1
            and malformed.entries[0].title == 'One' and not empty.bozo and empty.entries == [])
    elif task == 'FP-U02':
        parsed = parse_xml('<rss version="2.0"><channel><title>News</title><item><title>One</title><pubDate>Thu, 22 Oct 2026 09:00:00 +0200</pubDate></item></channel></rss>')
        item = parsed.entries[0]
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always')
            fallback = item.updated
        result['parsed_dates_are_utc_and_legacy_updated_fallback_is_not_a_real_key'] = (
            item.published_parsed[:6] == (2026, 10, 22, 7, 0, 0)
            and 'updated' not in item and not dict.__contains__(item, 'updated')
            and fallback == item.published and len(recorded) == 1
            and recorded[0].category is DeprecationWarning)
    elif task == 'FP-C01':
        xml = '<rss version="2.0"><channel><title>News</title><item><title>One</title><description><![CDATA[<script>alert(1)</script><b>Visible</b>]]></description></item></channel></rss>'
        default, raw = parse_xml(xml), parse_xml(xml, sanitize_html=False)
        result['html_sanitization_changes_markup_and_requires_a_downstream_rendering_policy'] = (
            default.entries[0].summary == '<b>Visible</b>'
            and '<script>alert(1)</script>' in raw.entries[0].summary)
    elif task == 'FP-C02':
        xml = '<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title><id>urn:feed</id><updated>2026-10-22T00:00:00Z</updated><entry><title>One</title><id>urn:one</id><updated>2026-10-22T00:00:00Z</updated><content type="html">&lt;a href="doc"&gt;One&lt;/a&gt;</content></entry></feed>'
        options = {'response_headers': {'content-location': 'https://example.test/base/'}}
        default, relative = parse_xml(xml, **options), parse_xml(xml, resolve_relative_uris=False, **options)
        result['relative_html_uris_need_explicit_local_source_provenance'] = (
            'https://example.test/base/doc' in default.entries[0].content[0].value
            and 'href="doc"' in relative.entries[0].content[0].value)
    elif task == 'FP-P01':
        data = {'version': 'https://jsonfeed.org/version/1', 'title': 'News',
            'items': [{'id': 'one', 'content_text': 'Text', 'tags': ['tag'],
                'attachments': [{'url': 'https://example.test/a', 'mime_type': 'audio/ogg', 'size_in_bytes': 12}]}]}
        parsed = feedparser.parse(BytesIO(dumps(data).encode()), response_headers={'content-type': 'application/feed+json'})
        item = parsed.entries[0]
        enclosure_failure = False
        try:
            item.enclosures
        except AttributeError:
            enclosure_failure = True
        result['json_feed_raw_storage_and_legacy_accessors_need_an_explicit_normalization_layer'] = (
            isinstance(dict.__getitem__(item, 'content'), dict)
            and dict.__getitem__(item, 'category') == ['tag']
            and dict.__getitem__(item, 'enclosures')[0]['href'] == 'https://example.test/a'
            and enclosure_failure)
    elif task == 'FP-D01':
        data = {'version': 'https://jsonfeed.org/version/1', 'title': 'News',
            'items': [{'id': 'one', 'date_modified': '2026-10-22T09:00:00+02:00', 'content_text': 'Text'}]}
        parsed = feedparser.parse(BytesIO(dumps(data).encode()), response_headers={'content-type': 'application/feed+json'})
        result.update(bozo=bool(parsed.bozo), modified_stored=dict.__contains__(parsed.entries[0], 'updated'),
            raw_source_modified=data['items'][0]['date_modified'])
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
