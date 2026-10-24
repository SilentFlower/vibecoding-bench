"""公开配置层合并回归。"""
import pytest
import tomlkit
from tomlkit.merging import merge_documents

def test_recursive_merge_preserves_base_comments_and_inputs():
    base=tomlkit.parse('# header\n[a]\nx=1 # keep\ny=2\n')
    result=merge_documents(base,{'a':{'y':3,'z':4}})
    assert result.unwrap()=={'a':{'x':1,'y':3,'z':4}} and '# keep' in result.as_string()
    assert base['a']['y']==2

def test_array_policies_are_explicit():
    base=tomlkit.parse('a=[1,2]\n')
    assert merge_documents(base,{'a':[2,3]},arrays='replace')['a']==[2,3]
    assert merge_documents(base,{'a':[2,3]},arrays='append')['a']==[1,2,2,3]
    assert merge_documents(base,{'a':[2,3]},arrays='unique')['a']==[1,2,3]

def test_conflict_error_leaves_original_byte_identical():
    base=tomlkit.parse('a=1\n');before=base.as_string()
    with pytest.raises(ValueError):
        merge_documents(base,{'a':2},conflicts='error')
    assert base.as_string()==before

def test_incoming_nodes_are_not_shared_and_invalid_policy_fails():
    overlay={'a':[{'x':1}]}
    result=merge_documents(tomlkit.document(),overlay)
    result['a'][0]['x']=2
    assert overlay=={'a':[{'x':1}]}
    with pytest.raises(ValueError):
        merge_documents(tomlkit.document(),{},arrays='guess')
