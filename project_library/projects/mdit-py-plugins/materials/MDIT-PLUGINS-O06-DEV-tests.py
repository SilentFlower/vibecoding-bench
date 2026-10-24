"Public regression tests for MDIT-PLUGINS-O06-DEV; the complete business contract is in materials/MDIT-PLUGINS-O06-DEV-contract.md."
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
import pytest

def test_callback_matches_deduplicated_rendered_ids_and_source_map():
    "Verify callback matches deduplicated rendered ids and source map."
    records=[];md=MarkdownIt().use(anchors_plugin,callback=records.append)
    html=md.render('# A\n\n# A\n\n## B')
    assert [record['slug'] for record in records]==['a','a-1','b']
    assert records[0]=={'title':'A','slug':'a','level':1,'map':[0,1]}
    assert records[-1]['map']==[4,5] and all('id="'+record['slug']+'"' in html for record in records)

def test_title_excludes_permalink_and_records_do_not_modify_tokens():
    "Verify title excludes permalink and records do not modify tokens."
    records=[]
    def record(value):records.append(dict(value));value['map'][0]=999
    md=MarkdownIt().use(anchors_plugin,callback=record,permalink=True,slug_func=lambda title:'fixed')
    tokens=md.parse('# **Bold** `code`\n\n# Next')
    assert records[0]['title']=='Bold code' and records[1]['slug']=='fixed-1'
    assert tokens[0].map==[0,1] and tokens[0].attrGet('id')=='fixed'

def test_selected_levels_each_parse_and_callback_errors_are_explicit():
    "Verify selected levels each parse and callback errors are explicit."
    records=[];md=MarkdownIt().use(anchors_plugin,min_level=2,max_level=2,callback=records.append)
    tokens=md.parse('# Skip\n\n## A');md.renderer.render(tokens,md.options,{})
    assert len(records)==1 and records[0]['level']==2
    md.render('## A');assert records[-1]['slug']=='a' and len(records)==2
    def fail(record):raise RuntimeError('consumer failed')
    with pytest.raises(RuntimeError):MarkdownIt().use(anchors_plugin,callback=fail).render('# A')
