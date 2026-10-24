"Public regression tests for PA-BENEATH-DEV; the complete business contract is in materials/PA-BENEATH-DEV-contract.md."
from path import Path
import pytest

def test_nested_and_equal_paths_return_relative_path_types(tmp_path):
    root=Path(tmp_path)
    result=(root/'nested'/'file').relative_beneath(root)
    assert isinstance(result,Path) and result=='nested/file' and root.relative_beneath(root)=='.'

def test_sibling_prefix_and_parent_escape_are_rejected(tmp_path):
    root=Path(tmp_path/'root')
    for target in (Path(str(root)+'-other')/'file',root/'..'/'outside'):
        with pytest.raises(ValueError):
            target.relative_beneath(root)

def test_nonexistent_paths_are_valid_lexical_inputs(tmp_path):
    root=Path(tmp_path/'absent')
    assert (root/'child').relative_beneath(root)=='child' and not root.exists()

def test_symlink_is_not_resolved_by_lexical_operation(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();root=tmp_path/'root';root.mkdir();(root/'link').symlink_to(outside,target_is_directory=True)
    assert Path(root/'link'/'file').relative_beneath(root)=='link/file'
