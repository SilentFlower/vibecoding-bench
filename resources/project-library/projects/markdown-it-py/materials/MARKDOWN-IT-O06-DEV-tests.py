"Public regression tests for MARKDOWN-IT-O06-DEV; the complete business contract is in materials/MARKDOWN-IT-O06-DEV-contract.md."
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from markdown_it.token import Token
import pytest

def test_move_paragraph_between_containers_updates_render_and_siblings():
    "Verify move paragraph between containers updates render and siblings."
    md=MarkdownIt();tree=SyntaxTreeNode(md.parse('first\n\n> nested\n\nlast'))
    first,quote,last=tree.children;quote.append_child(last)
    assert last.parent is quote and tree.children==[first,quote] and quote.children[-1] is last
    assert last.previous_sibling is quote.children[0] and last.next_sibling is None
    html=md.renderer.render(tree.to_tokens(),md.options,{})
    assert html=='<p>first</p>\n<blockquote>\n<p>nested</p>\n<p>last</p>\n</blockquote>\n'

def test_inline_edits_replace_remove_and_same_parent_move_sync_tokens():
    "Verify inline edits replace remove and same parent move sync tokens."
    md=MarkdownIt();tree=SyntaxTreeNode(md.parse('old'))
    inline=tree.children[0].children[0];old=inline.children[0]
    new=SyntaxTreeNode([Token('text','',0,content='new')],create_root=False)
    assert inline.replace_child(old,new) is old and old.parent is None
    tail=SyntaxTreeNode([Token('text','',0,content='!')],create_root=False);inline.append_child(tail)
    assert md.renderer.render(tree.to_tokens(),md.options,{})=='<p>new!</p>\n'
    inline.insert_child(0,tail);assert inline.children==[tail,new]
    inline.remove_child(tail);assert tail.parent is None and md.renderer.render(tree.to_tokens(),md.options,{})=='<p>new</p>\n'

def test_rejected_cycles_roots_and_invalid_indices_leave_tree_intact():
    "Verify rejected cycles roots and invalid indices leave tree intact."
    md=MarkdownIt();tree=SyntaxTreeNode(md.parse('a\n\n> b'));paragraph,quote=tree.children;before=tree.to_tokens()
    with pytest.raises(ValueError):quote.append_child(tree)
    with pytest.raises(ValueError):quote.children[0].append_child(quote)
    with pytest.raises(IndexError):quote.insert_child(99,paragraph)
    with pytest.raises(ValueError):paragraph.children[0].children[0].append_child(quote)
    assert tree.children==[paragraph,quote] and paragraph.parent is tree and tree.to_tokens()==before
