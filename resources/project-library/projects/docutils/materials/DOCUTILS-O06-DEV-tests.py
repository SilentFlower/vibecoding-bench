"Public regression tests for DOCUTILS-O06-DEV; the complete business contract is in materials/DOCUTILS-O06-DEV-contract.md."
from docutils.core import publish_doctree,publish_from_doctree
from docutils import nodes
import io
import pytest

def build(source):
    "Support the public regression through build."
    return publish_doctree(source,source_path='source.rst',settings_overrides={'warning_stream':io.StringIO(),'halt_level':6,'report_level':5,'doctitle_xform':False})

def test_selected_second_section_internal_refs_source_and_old_tree_are_preserved():
    "Verify selected second section internal refs source and old tree are preserved."
    from docutils.fragments import extract_section
    document=build('First\n=====\n\nFirst body.\n\nSecond\n======\n\n.. _local:\n\nSecond **body** and local_.\n');before=document.pformat()
    original=[node for node in document.findall(nodes.section) if 'second' in node['ids']][0]
    extracted=extract_section(document,'second');section=next(extracted.findall(nodes.section))
    assert section.source==original.source and section.line==original.line and 'First body' not in extracted.astext() and 'Second body' in extracted.astext()
    assert document.pformat()==before and next(extracted.findall(nodes.reference))['refid'] in extracted.ids
    html=publish_from_doctree(extracted,writer='html5').decode('utf8');assert 'Second' in html and 'First body' not in html

def test_external_footnote_is_rejected_or_included_with_closed_backrefs():
    "Verify external footnote is rejected or included with closed backrefs."
    from docutils.fragments import extract_section
    document=build('.. [1] Shared note.\n\nSection\n=======\n\nUse [1]_.\n')
    with pytest.raises(ValueError):extract_section(document,'section')
    extracted=extract_section(document,'section',external='include_notes')
    assert 'Shared note.' in extracted.astext() and len(list(extracted.findall(nodes.footnote)))==1
    for node in extracted.findall(nodes.Element):
        if 'refid' in node:assert node['refid'] in extracted.ids
        assert all(identifier in extracted.ids for identifier in node.get('backrefs',[]))

def test_missing_duplicate_id_external_section_and_invalid_policy_do_not_mutate():
    "Verify missing duplicate id external section and invalid policy do not mutate."
    from docutils.fragments import extract_section
    document=build('First\n=====\n\nFirst body.\n\nSecond\n======\n\nSee First_.\n');before=document.pformat()
    with pytest.raises(KeyError):extract_section(document,'missing')
    with pytest.raises(ValueError):extract_section(document,'second',external='include_notes')
    with pytest.raises(ValueError):extract_section(document,'first',external='guess')
    assert document.pformat()==before
