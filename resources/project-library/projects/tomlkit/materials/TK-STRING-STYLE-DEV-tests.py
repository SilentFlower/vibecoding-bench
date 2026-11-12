"Public regression tests for TK-STRING-STYLE-DEV; the complete business contract is in materials/TK-STRING-STYLE-DEV-contract.md."
import pytest
import tomlkit
from tomlkit.exceptions import InvalidStringError

def test_quote_type_and_comment_are_preserved():
    document=tomlkit.parse("a = 'old' # keep\n")
    old=document.item('a');new=old.replace_value('new')
    document['a']=new
    assert document.as_string()=="a = 'new' # keep\n" and str(old)=='old'

def test_unrepresentable_literal_requires_explicit_fallback():
    old=tomlkit.string('old',literal=True)
    with pytest.raises(InvalidStringError):
        old.replace_value("can't")
    new=old.replace_value("can't",fallback=True)
    assert new.type.is_basic() and tomlkit.parse('a='+new.as_string())['a']=="can't"

def test_multiline_leading_newline_roundtrips():
    old=tomlkit.string('old',multiline=True)
    new=old.replace_value('\nnew\nvalue')
    assert new.type==old.type and tomlkit.parse('a='+new.as_string())['a']=='\nnew\nvalue'

def test_trivia_is_independent_and_plain_str_replace_is_unchanged():
    old=tomlkit.string('old');old.comment('original')
    new=old.replace_value('new');new.comment('new comment')
    assert 'original' in old.trivia.comment and 'new comment' in new.trivia.comment
    assert old.replace('o','b')=='bld'
