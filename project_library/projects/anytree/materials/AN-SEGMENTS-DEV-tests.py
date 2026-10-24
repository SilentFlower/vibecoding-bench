"Public regression tests for AN-SEGMENTS-DEV; the complete business contract is in materials/AN-SEGMENTS-DEV-contract.md."
import pytest
from anytree import Node, Resolver, ChildResolverError, ResolverError

def test_slash_and_navigation_text_are_literal_names():
    root = Node('root')
    slash = Node('a/b', parent=root)
    dot = Node('..', parent=slash)
    assert Resolver().get_by_segments(root, ['a/b', '..']) is dot

def test_empty_and_wildcard_names_are_literal():
    root = Node('root')
    empty = Node('', parent=root)
    wildcard = Node('*', parent=empty)
    assert Resolver().get_by_segments(root, ['', '*']) is wildcard
    assert Resolver().get_by_segments(root, []) is root

def test_case_and_custom_attribute_modes_are_preserved():
    root = Node('root', key='ROOT')
    child = Node('child', key='A/B', parent=root)
    assert Resolver('key', ignorecase=True).get_by_segments(root, ['a/b']) is child

def test_relax_stops_at_the_first_missing_segment():
    root = Node('root')
    assert Resolver(relax=True).get_by_segments(root, ['missing', 'next']) is None
    with pytest.raises(ChildResolverError):
        Resolver().get_by_segments(root, ['missing'])

def test_absolute_mode_matches_an_explicit_root_segment():
    root = Node('root')
    child = Node('child', parent=root)
    assert Resolver().get_by_segments(child, ['root', 'child'], absolute=True) is child
    with pytest.raises(ResolverError):
        Resolver().get_by_segments(child, ['other'], absolute=True)

def test_string_and_nonstring_segments_are_rejected_and_old_get_keeps_navigation():
    root = Node('root')
    child = Node('child', parent=root)
    with pytest.raises(TypeError):
        Resolver().get_by_segments(root, 'child')
    with pytest.raises(TypeError):
        Resolver().get_by_segments(root, [3])
    assert Resolver().get(child, '..') is root
