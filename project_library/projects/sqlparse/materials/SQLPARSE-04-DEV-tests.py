"""查询形状忽略业务字面量而保留表名、操作和真实占位符。"""
from sqlparse.fingerprint import fingerprint


def test_literal_comment_and_keyword_normalization():
    """不同值与注释得到同形状，字符串内注释符不是注释。@return None。"""
    a="select * from products where id=-1 and label='-- secret'; -- tail"
    b="SELECT * FROM products WHERE id=99 AND label='other';"
    assert fingerprint(a)==fingerprint(b)
    assert 'secret' not in fingerprint(a) and '99' not in fingerprint(b)
    assert fingerprint('select $$raw ; -- content$$')==fingerprint("select 'different'")


def test_identity_quoted_names_placeholders_and_list_cardinality_remain():
    """形状等同不冒称SQL语义相等，列表长度政策明确保留。@return None。"""
    assert fingerprint('select * from a')!=fingerprint('select * from b')
    assert fingerprint('select "Sensitive.Name" from t')!='SELECT ? FROM t'
    assert ':value' in fingerprint('select :value from t')
    assert fingerprint('select x from t where x in (1,2)')!=fingerprint('select x from t where x in (1)')
    assert fingerprint('select null,true')==fingerprint('select false,null')
    assert fingerprint('select true',replace_constants=False)=='SELECT TRUE'

