"""所选extras按每个singular绑定求值，不能跨extra拼接条件。"""
from packaging.requirements import Requirement

def test_selected_extras_normalization_empty_and_no_marker():
    """test/docs任一满足，空集合使用基础extra。@return None。"""
    requirement=Requirement('library; extra == "some-extra"')
    assert requirement.applies({'docs','Some_Extra'}) and not requirement.applies({'docs'})
    assert Requirement('library').applies(()) and Requirement('library; extra == ""').applies(())
    assert not Requirement('library; extra == "test"').applies(())

def test_same_binding_environment_and_source_ownership():
    """and两边必须使用同一个extra，来源映射不改。@return None。"""
    requirement=Requirement('library; extra == "test" and extra == "docs"')
    assert not requirement.applies({'test','docs'})
    environment={'os_name':'target','extra':'not-selected'}
    assert Requirement('library; extra == "test" and os_name == "target"').applies(['test'],environment)
    assert environment=={'os_name':'target','extra':'not-selected'}

