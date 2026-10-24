"""递归合并既保留注释，也不把源Section挂进目标。"""
from configobj import ConfigObj

def test_new_subsection_metadata_and_parent_isolation():
    """新增节和叶注释保留，复制后父树正确。@return None。"""
    target=ConfigObj(['root=target'])
    source=ConfigObj(['root=source','# section note','[child]','# leaf note','x=%(root)s # inline'])
    target.merge(source)
    assert target.comments['child']==['# section note'] and target['child'].comments['x']==['# leaf note']
    assert target['child'].inline_comments['x']=='# inline' and target['child'].parent is target
    target['root']='changed';assert target['child']['x']=='changed' and source['child']['x']=='source'

def test_conflict_policy_and_idempotent_comments():
    """冲突明确且重复merge不叠加注释。@return None。"""
    left=ConfigObj(['prefix=ok','# old','x=1']);right=ConfigObj(['prefix=ok','# incoming','x=2'])
    left.merge(right,comments='existing');assert left.comments['x']==['# old'] and left['x']=='2'
    left.merge(right);left.merge(right);assert left.comments['x']==['# incoming']

def test_plain_mapping_preserves_existing_comment():
    """普通dict没有注释元数据，不能抹除已有注释。@return None。"""
    import pytest
    left=ConfigObj(['prefix=ok','# retained','x=1']);left.merge({'x':'2','child':{'y':'3'}})
    assert left.comments['x']==['# retained'] and left['child'].parent is left
    with pytest.raises(ValueError):left.merge({},comments='bad')
