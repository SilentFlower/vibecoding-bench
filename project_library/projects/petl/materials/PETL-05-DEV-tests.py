"Public regression tests for PETL-05-DEV; the complete business contract is in materials/PETL-05-DEV-contract.md."
import unittest
import petl

def test_casefold_target_and_rows_and_complement_keep_original_text():
    "Verify casefold target and rows and complement keep original text."
    table=[['name','id'],['Straße',1],['STRASSE',2],['Other',3]]
    assert list(petl.selecteq(table,'name','strasse',key=str.casefold))==[('name','id'),('Straße',1),('STRASSE',2)]
    assert list(petl.wrap(table).selecteq('name','STRASSE',complement=True,key=str.casefold))==[('name','id'),('Other',3)]
    assert list(petl.selecteq(table,'name','strasse'))==[('name','id')]

def test_none_falsey_key_and_callback_errors_are_explicit():
    "Verify none falsey key and callback errors are explicit."
    class Key:
        "Public regression fixture: Key."
        def __bool__(self):return False
        def __call__(self,value):return '' if value is None else str(value)
    table=[['value'],[None],[''],[3]]
    assert list(petl.selecteq(table,'value','',key=Key()))==[('value',),(None,),('',)]
    with unittest.TestCase().assertRaises(TypeError):petl.selecteq(table,'value',3,key=False)

