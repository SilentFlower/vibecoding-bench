"""导航回调必须拿到最终真实slug，不能拿未去重的候选。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
import pytest

def test_callback_matches_deduplicated_rendered_ids_and_source_map():
    """重复标题记录与实际HTML id/位置一一对应。@return None。"""
    records=[];md=MarkdownIt().use(anchors_plugin,callback=records.append)
    html=md.render('# A\n\n# A\n\n## B')
    assert [record['slug'] for record in records]==['a','a-1','b']
    assert records[0]=={'title':'A','slug':'a','level':1,'map':[0,1]}
    assert records[-1]['map']==[4,5] and all('id="'+record['slug']+'"' in html for record in records)

def test_title_excludes_permalink_and_records_do_not_modify_tokens():
    """回调在permalink注入前读取原文字，副本map不可污染真实范围。@return None。"""
    records=[]
    def record(value):records.append(dict(value));value['map'][0]=999
    md=MarkdownIt().use(anchors_plugin,callback=record,permalink=True,slug_func=lambda title:'fixed')
    tokens=md.parse('# **Bold** `code`\n\n# Next')
    assert records[0]['title']=='Bold code' and records[1]['slug']=='fixed-1'
    assert tokens[0].map==[0,1] and tokens[0].attrGet('id')=='fixed'

def test_selected_levels_each_parse_and_callback_errors_are_explicit():
    """按选择级别记录，每份文档重新去重；render已有Token不重复回调。@return None。"""
    records=[];md=MarkdownIt().use(anchors_plugin,min_level=2,max_level=2,callback=records.append)
    tokens=md.parse('# Skip\n\n## A');md.renderer.render(tokens,md.options,{})
    assert len(records)==1 and records[0]['level']==2
    md.render('## A');assert records[-1]['slug']=='a' and len(records)==2
    def fail(record):raise RuntimeError('consumer failed')
    with pytest.raises(RuntimeError):MarkdownIt().use(anchors_plugin,callback=fail).render('# A')
