"""公开受控目录遍历回归。"""
from path import Path
import pytest

def test_stable_preorder_depth_and_exclusion(tmp_path):
    (tmp_path/'b').mkdir();(tmp_path/'a').mkdir();(tmp_path/'a'/'x').write_text('x');(tmp_path/'b'/'y').write_text('y')
    root=Path(tmp_path)
    assert [str(p.relpath(root)) for p in root.walk_controlled(stable=True,exclude=['b'])]==['a','a/x']
    assert [p.basename() for p in root.walk_controlled(max_depth=1,stable=True)]==['a','b']

def test_links_are_yielded_but_not_followed_by_default(tmp_path):
    directory=tmp_path/'real';directory.mkdir();(directory/'file').write_text('x');(tmp_path/'link').symlink_to(directory,target_is_directory=True)
    names=[str(p.relpath(tmp_path)) for p in Path(tmp_path).walk_controlled(stable=True)]
    assert names==['link','real','real/file']

def test_followed_link_cycles_terminate_and_do_not_duplicate_subtrees(tmp_path):
    directory=tmp_path/'real';directory.mkdir();(directory/'back').symlink_to(tmp_path,target_is_directory=True)
    result=list(Path(tmp_path).walk_controlled(follow_symlinks=True,stable=True))
    assert [str(p.relpath(tmp_path)) for p in result]==['real','real/back']

def test_invalid_and_zero_depth_are_explicit(tmp_path):
    assert list(Path(tmp_path).walk_controlled(max_depth=0))==[]
    with pytest.raises(ValueError):
        list(Path(tmp_path).walk_controlled(max_depth=True))
