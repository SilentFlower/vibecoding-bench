"Public regression tests for PETL-02-DEV; the complete business contract is in materials/PETL-02-DEV-contract.md."
import petl

def test_mixed_numeric_fields_have_ordered_issues_without_raw_values():
    "Verify mixed numeric fields have ordered issues without raw values."
    source=[['qty','price'],['2','3.5'],['private','bad']]
    table,issues=petl.convert_report(source,{'qty':int,'price':float})
    assert list(table)==[('qty','price'),(2,3.5),(None,None)]
    assert list(issues)==[('row','field','error_type'),(2,'qty','ValueError'),(2,'price','ValueError')]
    assert 'private' not in repr(issues)

def test_one_shot_source_replay_short_row_and_empty():
    "Verify one shot source replay short row and empty."
    count=[]
    def source():
        for row in [('qty','other'),('3','x'),()]:count.append(1);yield row
    table,issues=petl.convert_report(source(),{'qty':int},errorvalue='ERR')
    assert list(table)==[('qty','other'),(3,'x'),('ERR',)] and len(count)==3
    assert list(issues)[-1]==(2,'qty','IndexError') and list(table)==list(table)
    assert petl.convert_report(iter(()),{'qty':int})==((),(('row','field','error_type'),))

