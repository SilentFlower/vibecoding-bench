"""公开回归只测试授权的Atom链接序列化行为。"""
import unittest

from feedgen.entry import FeedEntry


class AtomLinkTests(unittest.TestCase):
    """覆盖完整元数据、多链接和空属性语义。"""

    def make_entry(self) -> FeedEntry:
        """构造有效的合成条目。@return 条目。"""
        item = FeedEntry()
        item.id('urn:test:1')
        item.title('Test')
        item.content('Text')
        return item

    def test_all_attributes_and_zero_length(self) -> None:
        """非空字符串元数据和零长度字符串全部保留。@return None。"""
        item = self.make_entry()
        link = {'href': 'https://example.test/page', 'rel': 'alternate', 'type': 'text/html',
            'hreflang': 'zh', 'title': '报告', 'length': '0'}
        item.link(link.copy())
        self.assertEqual(dict(item.atom_entry().find('link').attrib), link)

    def test_multiple_links_do_not_share_metadata(self) -> None:
        """多个关系保留独立属性且不修改输入状态。@return None。"""
        item = self.make_entry()
        first = {'href': 'https://example.test/a', 'rel': 'alternate', 'title': 'A'}
        second = {'href': 'https://example.test/b', 'rel': 'enclosure', 'length': '12', 'type': 'audio/ogg'}
        item.link([first.copy(), second.copy()])
        self.assertEqual([dict(node.attrib) for node in item.atom_entry().findall('link')], [first, second])
        self.assertEqual(item.link(), [first, second])

    def test_optional_empty_values_stay_omitted(self) -> None:
        """缺省关系仍保留，空或None的可选属性不凭空写出。@return None。"""
        item = self.make_entry()
        item.link(href='https://example.test/a', title='', type=None)
        self.assertEqual(dict(item.atom_entry().find('link').attrib),
            {'href': 'https://example.test/a', 'rel': 'alternate'})


if __name__ == '__main__':
    unittest.main()
