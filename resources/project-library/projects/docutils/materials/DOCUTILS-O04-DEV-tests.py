"Public regression tests for DOCUTILS-O04-DEV; the complete business contract is in materials/DOCUTILS-O04-DEV-contract.md."
from docutils.core import publish_parts,publish_doctree
from docutils import nodes
import io

def settings():
    "Support the public regression through settings."
    return {'warning_stream':io.StringIO(),'halt_level':6,'report_level':5}

def test_collapsible_expanded_inline_summary_and_escaped_body():
    "Verify collapsible expanded inline summary and escaped body."
    source='.. admonition:: Read **more**\n   :collapsible:\n   :expanded:\n\n   Body <unsafe>\n'
    html=publish_parts(source,writer='html5',settings_overrides=settings())['html_body']
    assert '<details' in html and 'open="open"' in html and '<summary>' in html and '<strong>more</strong>' in html
    assert html.count('Read ')==1 and '&lt;unsafe&gt;' in html and '</summary>' in html and '</details>' in html

def test_specific_note_nested_admonitions_default_closed_and_plain_fallback():
    "Verify specific note nested admonitions default closed and plain fallback."
    source='.. note::\n   :collapsible:\n\n   Outer\n\n   .. admonition:: Inner\n      :collapsible:\n\n      Inner body\n'
    html=publish_parts(source,writer='html5',settings_overrides=settings())['html_body']
    assert html.count('<details')==html.count('</details>')==2 and html.count('<summary')==2 and 'open=' not in html
    assert 'Outer' in html and 'Inner body' in html
    normal=publish_parts('.. note:: Body\n',writer='html5',settings_overrides=settings())['html_body'];assert '<aside' in normal and '<details' not in normal

def test_expanded_without_collapse_rejects_and_other_writer_keeps_visible_text():
    "Verify expanded without collapse rejects and other writer keeps visible text."
    bad=publish_doctree('.. note::\n   :expanded:\n\n   Body\n',settings_overrides=settings());assert list(bad.findall(nodes.system_message))
    output=publish_parts('.. admonition:: Title\n   :collapsible:\n\n   Body\n',writer='pseudoxml',settings_overrides=settings())['whole']
    assert 'Title' in output and 'Body' in output
