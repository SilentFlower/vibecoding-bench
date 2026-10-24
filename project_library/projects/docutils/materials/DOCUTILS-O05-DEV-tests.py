"""标准doctree JSON可独立重建真实节点并再发布，不使用pickle。"""
from docutils.core import publish_doctree,publish_string,publish_from_doctree
from docutils import nodes
import io,json,copy
import pytest

def settings():
    """构建真实可解析配置。@return 配置。"""
    return {'warning_stream':io.StringIO(),'halt_level':6,'report_level':5}

def test_json_writer_and_reader_preserve_chinese_ids_refs_and_real_node_types():
    """writer产物经json读取再建doctree，引用与真实HTML仍对应。@return None。"""
    from docutils.doctree_json import loads,dumps
    source='.. _target:\n\n章节\n====\n\n中文 **重点** and target_.\n'
    original=publish_doctree(source,source_path='source.rst',settings_overrides=settings())
    encoded=publish_string(source,writer='json',settings_overrides=settings());assert json.loads(encoded)['schema']==1
    rebuilt=loads(dumps(original),settings=original.settings)
    assert rebuilt.astext()==original.astext() and isinstance(next(rebuilt.findall(nodes.strong)),nodes.strong)
    assert next(rebuilt.findall(nodes.reference))['refid'] in rebuilt.ids
    html=publish_from_doctree(rebuilt,writer='html5',settings_overrides=settings()).decode('utf8');assert '中文' in html and '<strong>重点</strong>' in html

def test_sources_attributes_and_detached_roundtrip_remain_exact():
    """实际source/line/attrs/children保持，修改副本不污染原树。@return None。"""
    from docutils.doctree_json import to_data,from_data
    original=publish_doctree('Title\n=====\n\nParagraph.\n',source_path='input.rst',settings_overrides=settings())
    data=to_data(original);rebuilt=from_data(data,settings=original.settings)
    assert to_data(rebuilt)==data
    paragraph=next(rebuilt.findall(nodes.paragraph));paragraph['classes'].append('new')
    assert not next(original.findall(nodes.paragraph))['classes']

def test_unknown_schema_nodes_shapes_cycles_depth_and_opaque_attributes_reject():
    """任意节点/属性不能变成执行入口或无界递归。@return None。"""
    from docutils.doctree_json import to_data,from_data
    document=publish_doctree('Text',settings_overrides=settings());data=to_data(document)
    bad=copy.deepcopy(data);bad['schema']=99
    with pytest.raises(ValueError):from_data(bad)
    bad=copy.deepcopy(data);bad['root']['children'][0]['node']='__import__'
    with pytest.raises(ValueError):from_data(bad)
    with pytest.raises(ValueError):to_data(document,max_nodes=1)
    document['opaque']=object()
    with pytest.raises(ValueError):to_data(document)
