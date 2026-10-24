# Business scope

Implement the narrowly authorized link metadata repair and meaningful public regressions. Preserve all original controls and run the full applicable original regression.

# Investigation topics



# Supplied business material: materials/link-repair.md

Repair the pinned FeedEntry.atom_entry serialization so each link keeps all supported nonempty string attributes rel,type,hreflang,title,length as well as href. Keep independent links in order,Unicode titles and length="0";omit absent/None/empty optional values,retain the link setter default alternate and preserve input dictionaries,RSS selection and feed-level behavior. The original overwrites its link dictionary with an XML Element. Authorization is only library/feedgen/entry.py and meaningful public regression tests at app/test_atom_link.py. Preserve all original tests,configuration and other features. No unrelated extension or network request is authorized.


# Supplied business material: materials/public-test-example.py

"""Public regressions cover only the authorized Atom link serialization behavior."""
import unittest

from feedgen.entry import FeedEntry


class AtomLinkTests(unittest.TestCase):
    """Cover complete metadata, multiple links, and empty-attribute semantics."""

    def make_entry(self) -> FeedEntry:
        """Build a valid synthetic entry. @return Entry."""
        item = FeedEntry()
        item.id('urn:test:1')
        item.title('Test')
        item.content('Text')
        return item

    def test_all_attributes_and_zero_length(self) -> None:
        """Preserve non-empty metadata strings and a length value of zero. @return None."""
        item = self.make_entry()
        link = {'href': 'https://example.test/page', 'rel': 'alternate', 'type': 'text/html',
            'hreflang': 'zh', 'title': '报告', 'length': '0'}
        item.link(link.copy())
        self.assertEqual(dict(item.atom_entry().find('link').attrib), link)

    def test_multiple_links_do_not_share_metadata(self) -> None:
        """Preserve independent attributes for multiple relations without mutating input state. @return None."""
        item = self.make_entry()
        first = {'href': 'https://example.test/a', 'rel': 'alternate', 'title': 'A'}
        second = {'href': 'https://example.test/b', 'rel': 'enclosure', 'length': '12', 'type': 'audio/ogg'}
        item.link([first.copy(), second.copy()])
        self.assertEqual([dict(node.attrib) for node in item.atom_entry().findall('link')], [first, second])
        self.assertEqual(item.link(), [first, second])

    def test_optional_empty_values_stay_omitted(self) -> None:
        """Preserve the default relation and omit optional attributes that are empty or None. @return None."""
        item = self.make_entry()
        item.link(href='https://example.test/a', title='', type=None)
        self.assertEqual(dict(item.atom_entry().find('link').attrib),
            {'href': 'https://example.test/a', 'rel': 'alternate'})


if __name__ == '__main__':
    unittest.main()

