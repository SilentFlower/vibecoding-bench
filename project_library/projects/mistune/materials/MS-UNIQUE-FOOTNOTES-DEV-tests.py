"Public regression tests for MS-UNIQUE-FOOTNOTES-DEV; the complete business contract is in materials/MS-UNIQUE-FOOTNOTES-DEV-contract.md."
from html.parser import HTMLParser
import mistune
from mistune.plugins.footnotes import footnotes

def markdown(renderer='html'):
    return mistune.create_markdown(renderer=renderer,plugins=[lambda md:footnotes(md,unique_refs=True)])

def test_repeated_note_has_unique_references_and_all_backlinks():
    result=markdown()('a[^x] b[^x] c[^x]\n\n[^x]: note')
    assert result.count('id="fnref-1"')==1 and 'id="fnref-1-2"' in result and 'id="fnref-1-3"' in result
    assert 'href="#fnref-1-2"' in result and 'href="#fnref-1-3"' in result and result.count('<li id="fn-1"')==1

def test_ast_occurrences_share_note_index_but_have_distinct_reference_numbers():
    result=markdown('ast')('a[^x] b[^x]\n\n[^x]: note')
    refs=[child for token in result for child in token.get('children',[]) if child['type']=='footnote_ref']
    assert [r['attrs']['reference_index'] for r in refs]==[1,2] and [r['attrs']['index'] for r in refs]==[1,1]

def test_document_reuse_resets_counts_and_unknown_references_are_literal():
    md=markdown();md('a[^x] b[^x]\n\n[^x]: note')
    result=md('a[^x] [^missing]\n\n[^x]: next')
    assert 'id="fnref-1"' in result and 'fnref-1-2' not in result and '[^missing]' in result

def test_legacy_default_keeps_original_single_reference_output():
    source='a[^x]\n\n[^x]: note'
    assert mistune.create_markdown(plugins=['footnotes'])(source)==markdown()(source)
    from mistune.toc import add_toc_hook
    md=markdown();add_toc_hook(md)
    result=md('# Heading[^x]\n\n[^x]: note')
    assert 'id="fnref-1"' in result and 'fnref-1-2' not in result
