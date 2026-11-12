"Public regression tests for HTML5LIB-O03-DEV; the complete business contract is in materials/HTML5LIB-O03-DEV-contract.md."
import io
import pytest

def test_named_tokens_attributes_entities_comments_and_positions_are_real():
    "Verify named tokens attributes entities comments and positions are real."
    from html5lib.tokenizer import iter_tokens
    tokens=list(iter_tokens('<!doctype html>\n<p title="a&amp;b">Hi &lt;x&gt;<!--note--></p>'))
    assert tokens[0]['type']=='Doctype'
    paragraph=next(token for token in tokens if token['type']=='StartTag');assert paragraph['name']=='p' and paragraph['data']['title']=='a&b'
    assert ''.join(token['data'] for token in tokens if token['type'] in ('Characters','SpaceCharacters')).strip()=='Hi <x>'
    assert next(token for token in tokens if token['type']=='Comment')['data']=='note'
    assert all(len(token['position'])==2 and token['position'][0]>=1 for token in tokens)

def test_bytes_encoding_error_filter_and_source_stream_ownership():
    "Verify bytes encoding error filter and source stream ownership."
    from html5lib.tokenizer import iter_tokens
    stream=io.BytesIO('<p>中文'.encode('utf8'));tokens=list(iter_tokens(stream,override_encoding='utf8'))
    assert not stream.closed and any(token.get('data')=='中文' for token in tokens)
    bad=list(iter_tokens('<p x="a" x="b">'))
    assert any(token['type']=='ParseError' for token in bad)
    assert all(token['type']!='ParseError' for token in iter_tokens('<p x="a" x="b">',include_errors=False))

def test_budget_detached_tokens_empty_and_partial_close_have_explicit_semantics():
    "Verify budget detached tokens empty and partial close have explicit semantics."
    from html5lib.tokenizer import iter_tokens,TokenLimitError
    iterator=iter_tokens('<p>a</p>',max_tokens=1);first=next(iterator);first['data']['changed']='value'
    with pytest.raises(TokenLimitError):next(iterator)
    assert list(iter_tokens('',max_tokens=0))==[]
    with pytest.raises(ValueError):list(iter_tokens('x',max_tokens=True))
    stream=io.StringIO('<p>a</p>');iterator=iter_tokens(stream);next(iterator);iterator.close();assert not stream.closed
