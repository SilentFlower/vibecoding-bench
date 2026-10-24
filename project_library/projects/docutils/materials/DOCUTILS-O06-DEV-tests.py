"""具名章节提取真实树并处理脚注闭包，不切HTML字符串。"""
from docutils.core import publish_doctree,publish_from_doctree
from docutils import nodes
import io
import pytest

def build(source):
    """保留章节结构与来源的真实解析。@return document。"""
    return publish_doctree(source,source_path='source.rst',settings_overrides={'warning_stream':io.StringIO(),'halt_level':6,'report_level':5,'doctitle_xform':False})

def test_selected_second_section_internal_refs_source_and_old_tree_are_preserved():
    """第二节提取后没有首节正文，内部引用仍有效且源行保持。@return None。"""
    from docutils.fragments import extract_section
    document=build('First\n=====\n\nFirst body.\n\nSecond\n======\n\n.. _local:\n\nSecond **body** and local_.\n');before=document.pformat()
    original=[node for node in document.findall(nodes.section) if 'second' in node['ids']][0]
    extracted=extract_section(document,'second');section=next(extracted.findall(nodes.section))
    assert section.source==original.source and section.line==original.line and 'First body' not in extracted.astext() and 'Second body' in extracted.astext()
    assert document.pformat()==before and next(extracted.findall(nodes.reference))['refid'] in extracted.ids
    html=publish_from_doctree(extracted,writer='html5').decode('utf8');assert 'Second' in html and 'First body' not in html

def test_external_footnote_is_rejected_or_included_with_closed_backrefs():
    """外部脚注必须明确选政策，包含后每条refid及backref都能在新树找到。@return None。"""
    from docutils.fragments import extract_section
    document=build('.. [1] Shared note.\n\nSection\n=======\n\nUse [1]_.\n')
    with pytest.raises(ValueError):extract_section(document,'section')
    extracted=extract_section(document,'section',external='include_notes')
    assert 'Shared note.' in extracted.astext() and len(list(extracted.findall(nodes.footnote)))==1
    for node in extracted.findall(nodes.Element):
        if 'refid' in node:assert node['refid'] in extracted.ids
        assert all(identifier in extracted.ids for identifier in node.get('backrefs',[]))

def test_missing_duplicate_id_external_section_and_invalid_policy_do_not_mutate():
    """不猜未知目标，不默默把整章外部依赖并入，失败原树保持。@return None。"""
    from docutils.fragments import extract_section
    document=build('First\n=====\n\nFirst body.\n\nSecond\n======\n\nSee First_.\n');before=document.pformat()
    with pytest.raises(KeyError):extract_section(document,'missing')
    with pytest.raises(ValueError):extract_section(document,'second',external='include_notes')
    with pytest.raises(ValueError):extract_section(document,'first',external='guess')
    assert document.pformat()==before
