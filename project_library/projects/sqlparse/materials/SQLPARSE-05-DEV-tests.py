"Public regression tests for SQLPARSE-05-DEV; the complete business contract is in materials/SQLPARSE-05-DEV-contract.md."
import unittest
from sqlparse.sql import Token
from sqlparse import tokens as T


def test_explicit_name_and_keyword_policy_keeps_original_value():
    "Verify explicit name and keyword policy keeps original value."
    name=Token(T.Name,'Products');keyword=Token(T.Keyword,'select')
    assert not name.match(T.Name,'products') and name.match(T.Name,'products',case_sensitive=False)
    assert keyword.match(T.Keyword,'SELECT') and not keyword.match(T.Keyword,'SELECT',case_sensitive=True)
    assert keyword.match(T.Keyword,'select',case_sensitive=True)
    assert name.value=='Products' and keyword.value=='select'


def test_regex_generators_unicode_and_type_mismatch():
    "Verify regex generators unicode and type mismatch."
    token=Token(T.Name,'Straße')
    assert token.match(T.Name,(value for value in ['other','STRASSE']),case_sensitive=False)
    assert token.match(T.Name,r'^STRA',regex=True,case_sensitive=False)
    assert not token.match(T.Name,r'^STRA',regex=True,case_sensitive=True)
    assert not token.match(T.Keyword,None,case_sensitive=False)
    with unittest.TestCase().assertRaises(ValueError):token.match(T.Name,'x',case_sensitive='no')

