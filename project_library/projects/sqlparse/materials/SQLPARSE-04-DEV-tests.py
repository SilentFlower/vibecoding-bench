"Public regression tests for SQLPARSE-04-DEV; the complete business contract is in materials/SQLPARSE-04-DEV-contract.md."
from sqlparse.fingerprint import fingerprint


def test_literal_comment_and_keyword_normalization():
    "Verify literal comment and keyword normalization."
    a="select * from products where id=-1 and label='-- secret'; -- tail"
    b="SELECT * FROM products WHERE id=99 AND label='other';"
    assert fingerprint(a)==fingerprint(b)
    assert 'secret' not in fingerprint(a) and '99' not in fingerprint(b)
    assert fingerprint('select $$raw ; -- content$$')==fingerprint("select 'different'")


def test_identity_quoted_names_placeholders_and_list_cardinality_remain():
    "Verify identity quoted names placeholders and list cardinality remain."
    assert fingerprint('select * from a')!=fingerprint('select * from b')
    assert fingerprint('select "Sensitive.Name" from t')!='SELECT ? FROM t'
    assert ':value' in fingerprint('select :value from t')
    assert fingerprint('select x from t where x in (1,2)')!=fingerprint('select x from t where x in (1)')
    assert fingerprint('select null,true')==fingerprint('select false,null')
    assert fingerprint('select true',replace_constants=False)=='SELECT TRUE'

