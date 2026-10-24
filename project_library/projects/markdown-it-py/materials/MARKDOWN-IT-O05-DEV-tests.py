"Public regression tests for MARKDOWN-IT-O05-DEV; the complete business contract is in materials/MARKDOWN-IT-O05-DEV-contract.md."
from markdown_it import MarkdownIt
from markdown_it.token import Token
import pytest

def test_deep_copy_isolates_real_parse_children_attrs_map_and_meta():
    "Verify deep copy isolates real parse children attrs map and meta."
    md=MarkdownIt();original=md.parse('![alt](image)')[1];original.map=[0,1];original.meta={'values':[1]}
    copied=original.deep_copy();image=copied.children[0]
    image.attrs['src']='new';image.children[0].content='new-alt';copied.map[0]=9;copied.meta['values'].append(2)
    assert original.children[0].attrs['src']=='image' and original.children[0].children[0].content=='alt'
    assert original.map==[0,1] and original.meta=={'values':[1]}
    assert 'new-alt' in md.renderer.renderInline(copied.children,md.options,{})

def test_meta_cycles_and_shared_aliases_are_preserved_only_inside_copy():
    "Verify meta cycles and shared aliases are preserved only inside copy."
    token=Token('text','',0);shared=[];token.meta={'a':shared,'b':shared};shared.append(token)
    copied=token.deep_copy()
    assert copied is not token and copied.meta['a'] is copied.meta['b']
    assert copied.meta['a'] is not shared and copied.meta['a'][0] is copied
    assert token.copy().meta is token.meta

def test_uncopyable_custom_meta_propagates_and_no_partial_mutation():
    "Verify uncopyable custom meta propagates and no partial mutation."
    class Opaque:
        "Public regression fixture: Opaque."
        def __deepcopy__(self,memo):raise RuntimeError('cannot-copy')
    item=Opaque();token=Token('text','',0,meta={'item':item})
    with pytest.raises(RuntimeError,match='cannot-copy'):token.deep_copy()
    assert token.meta['item'] is item
