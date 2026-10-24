"""转换结果与问题表同一次消费，默认不泄露原值。"""
import petl

def test_mixed_numeric_fields_have_ordered_issues_without_raw_values():
    """一行多字段失败分别记录来源行及类型。@return None。"""
    source=[['qty','price'],['2','3.5'],['private','bad']]
    table,issues=petl.convert_report(source,{'qty':int,'price':float})
    assert list(table)==[('qty','price'),(2,3.5),(None,None)]
    assert list(issues)==[('row','field','error_type'),(2,'qty','ValueError'),(2,'price','ValueError')]
    assert 'private' not in repr(issues)

def test_one_shot_source_replay_short_row_and_empty():
    """返回值可重复读取，源不会因问题表再消费。@return None。"""
    count=[]
    def source():
        for row in [('qty','other'),('3','x'),()]:count.append(1);yield row
    table,issues=petl.convert_report(source(),{'qty':int},errorvalue='ERR')
    assert list(table)==[('qty','other'),(3,'x'),('ERR',)] and len(count)==3
    assert list(issues)[-1]==(2,'qty','IndexError') and list(table)==list(table)
    assert petl.convert_report(iter(()),{'qty':int})==((),(('row','field','error_type'),))

