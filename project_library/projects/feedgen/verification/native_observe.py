"""观察固定订阅生成器的顺序、格式投影、日期与链接元数据。"""
from copy import deepcopy
from datetime import datetime, timezone
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import feedgen
from feedgen.entry import FeedEntry
from feedgen.feed import FeedGenerator


def entry() -> FeedEntry:
    """构造仅含合成内容的有效条目。@return 有效条目。"""
    item = FeedEntry()
    item.id('urn:document:1')
    item.title('Document')
    item.content('Text')
    item.updated(datetime(2026, 10, 22, tzinfo=timezone.utc))
    return item


def main() -> None:
    """只序列化本地合成信息，链接不产生网络请求。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(feedgen.__file__).resolve() == root / 'library/feedgen/__init__.py'}
    task = argv[1]
    if task == 'FG-U01':
        default, appended = FeedGenerator(), FeedGenerator()
        for name in ('first', 'second', 'third'):
            default.add_entry().id(name)
            appended.add_entry(order='append').id(name)
        result['default_prepend_and_explicit_append_have_different_document_order'] = (
            [item.id() for item in default.entry()] == ['third', 'second', 'first']
            and [item.id() for item in appended.entry()] == ['first', 'second', 'third'])
    elif task == 'FG-U02':
        item = entry()
        item.link(href='https://example.test/a', rel='alternate')
        item.link(href='https://example.test/b', rel='alternate')
        item.enclosure(url='https://example.test/one', length=3, type='audio/mpeg')
        item.enclosure(url='https://example.test/two', length=0, type='audio/ogg')
        rss = item.rss_entry()
        result['rss_projects_last_alternate_and_enclosure_while_atom_keeps_all_links'] = (
            rss.findtext('link') == 'https://example.test/b'
            and dict(rss.find('enclosure').attrib) == {'url': 'https://example.test/two', 'length': '0', 'type': 'audio/ogg'}
            and [node.get('href') for node in item.atom_entry().findall('link')] == [
                'https://example.test/a', 'https://example.test/b', 'https://example.test/one', 'https://example.test/two'])
    elif task == 'FG-C01':
        item = entry()
        failures = []
        for value in (datetime(2026, 10, 22), '2026-10-22T09:00:00'):
            try:
                item.published(value)
            except ValueError as error:
                failures.append(str(error))
        accepted = item.published('2026-10-22T09:00:00+02:00')
        result['dates_require_explicit_timezone_instead_of_guessing_source_zone'] = (
            failures == ['Datetime object has no timezone info'] * 2
            and accepted.isoformat() == '2026-10-22T09:00:00+02:00'
            and item.rss_entry().findtext('pubDate') == 'Thu, 22 Oct 2026 09:00:00 +0200')
    elif task == 'FG-C02':
        item = entry()
        initial = {'url': 'https://example.test/old', 'title': 'Original'}
        item.source(**initial)
        title_only = deepcopy(item.source(title='Edited'))
        url_only = deepcopy(item.source(url='https://example.test/new'))
        item.source(url='https://example.test/new', title='Edited')
        source = item.atom_entry().find('source')
        result['source_metadata_updates_require_both_url_and_title'] = (
            title_only == url_only == initial and source.findtext('title') == 'Edited'
            and source.find('link').get('href') == 'https://example.test/new')
    elif task == 'FG-P01':
        outputs = []
        stamp = datetime(2026, 10, 22, tzinfo=timezone.utc)
        for _ in range(2):
            feed = FeedGenerator()
            feed.id('urn:feed:1')
            feed.title('Documents')
            feed.description('Published documents')
            feed.link(href='https://example.test', rel='alternate')
            feed.updated(stamp)
            item = entry()
            item.published(stamp)
            feed.add_entry(item)
            outputs.append((feed.atom_str(), feed.rss_str()))
        result['explicit_feed_and_entry_dates_make_the_supplied_build_reproducible'] = (
            outputs[0] == outputs[1] and b'2026-10-22T00:00:00+00:00' in outputs[0][0]
            and b'Thu, 22 Oct 2026 00:00:00 +0000' in outputs[0][1])
    elif task == 'FG-D01':
        inline, external = entry(), entry()
        inline.content('AA==', type='application/octet-stream')
        error = None
        try:
            inline.atom_entry()
        except NotImplementedError as caught:
            error = str(caught)
        external.content(src='https://example.test/blob')
        result.update(inline_error=error, external_content=dict(external.atom_entry().find('content').attrib))
    elif task == 'FG-M01':
        item = entry()
        links = [
            {'href': 'https://example.test/page', 'rel': 'alternate', 'type': 'text/html',
                'hreflang': 'zh', 'title': '报告', 'length': '0'},
            {'href': 'https://example.test/audio', 'rel': 'enclosure', 'type': 'audio/mpeg', 'length': '42'},
            {'href': 'https://example.test/related', 'rel': 'related', 'title': '', 'length': None}]
        item.link(deepcopy(links))
        before = deepcopy(item.link())
        nodes = [dict(node.attrib) for node in item.atom_entry().findall('link')]
        wanted = [links[0], links[1], {'href': 'https://example.test/related', 'rel': 'related'}]
        rss = item.rss_entry()
        result['atom_entry_preserves_all_supported_nonempty_link_attributes'] = (
            nodes == wanted and item.link() == before
            and rss.findtext('link') == 'https://example.test/page'
            and dict(rss.find('enclosure').attrib) == {'url': 'https://example.test/audio', 'type': 'audio/mpeg', 'length': '42'})
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
