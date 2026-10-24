"""结构路径来源不改变普通Python值类型。"""
from yaml.marked import load_with_marks

def test_nested_paths_unicode_and_exact_source_slice():
    """路径中的键与列表索引准确，坐标不是UTF8字节偏移。@return None。"""
    text='name: 中文\nservice:\n  ports: [80, 443]\n'
    value,marks=load_with_marks(text)
    assert value=={'name':'中文','service':{'ports':[80,443]}}
    span=marks[('service','ports',1)]
    assert text[span.start:span.end]=='443' and span.line==2
    assert text[marks[('name',)].start:marks[('name',)].end]=='中文'

def test_alias_paths_share_value_origin_and_recursive_graph_terminates():
    """别名每个结构路径都指向原锚点位置，环不能无限展开。@return None。"""
    value,marks=load_with_marks('a: &a [1]\nb: *a')
    assert value['a'] is value['b'] and marks[('a',0)]==marks[('b',0)]
    value,marks=load_with_marks('&a [*a]')
    assert value[0] is value and (0,) in marks and len(marks)==2
    assert load_with_marks('')==(None,{})

