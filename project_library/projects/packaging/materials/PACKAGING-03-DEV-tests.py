"Public regression tests for PACKAGING-03-DEV; the complete business contract is in materials/PACKAGING-03-DEV-contract.md."
from packaging.requirements import Requirement

def test_selected_extras_normalization_empty_and_no_marker():
    "Verify selected extras normalization empty and no marker."
    requirement=Requirement('library; extra == "some-extra"')
    assert requirement.applies({'docs','Some_Extra'}) and not requirement.applies({'docs'})
    assert Requirement('library').applies(()) and Requirement('library; extra == ""').applies(())
    assert not Requirement('library; extra == "test"').applies(())

def test_same_binding_environment_and_source_ownership():
    "Verify same binding environment and source ownership."
    requirement=Requirement('library; extra == "test" and extra == "docs"')
    assert not requirement.applies({'test','docs'})
    environment={'os_name':'target','extra':'not-selected'}
    assert Requirement('library; extra == "test" and os_name == "target"').applies(['test'],environment)
    assert environment=={'os_name':'target','extra':'not-selected'}

