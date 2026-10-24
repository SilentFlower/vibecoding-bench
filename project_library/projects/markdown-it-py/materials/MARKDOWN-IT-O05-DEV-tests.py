"""深复制保护解析缓存，同时旧copy保留浅复制语义。"""
from markdown_it import MarkdownIt
from markdown_it.token import Token
import pytest

def test_deep_copy_isolates_real_parse_children_attrs_map_and_meta():
    """修改各层缓存内容不反写原文档，实际渲染可分别变换。@return None。"""
    md=MarkdownIt();original=md.parse('![alt](image)')[1];original.map=[0,1];original.meta={'values':[1]}
    copied=original.deep_copy();image=copied.children[0]
    image.attrs['src']='new';image.children[0].content='new-alt';copied.map[0]=9;copied.meta['values'].append(2)
    assert original.children[0].attrs['src']=='image' and original.children[0].children[0].content=='alt'
    assert original.map==[0,1] and original.meta=={'values':[1]}
    assert 'new-alt' in md.renderer.renderInline(copied.children,md.options,{})

def test_meta_cycles_and_shared_aliases_are_preserved_only_inside_copy():
    """循环和多个键的别名仍是副本自己的对象图。@return None。"""
    token=Token('text','',0);shared=[];token.meta={'a':shared,'b':shared};shared.append(token)
    copied=token.deep_copy()
    assert copied is not token and copied.meta['a'] is copied.meta['b']
    assert copied.meta['a'] is not shared and copied.meta['a'][0] is copied
    assert token.copy().meta is token.meta

def test_uncopyable_custom_meta_propagates_and_no_partial_mutation():
    """不可复制值拒绝而非悄悄共享，原始token事实不变。@return None。"""
    class Opaque:
        """真实声明不能复制的业务值。"""
        def __deepcopy__(self,memo):raise RuntimeError('cannot-copy')
    item=Opaque();token=Token('text','',0,meta={'item':item})
    with pytest.raises(RuntimeError,match='cannot-copy'):token.deep_copy()
    assert token.meta['item'] is item
