"""归一化只用于比较，返回原始业务值与惰性表语义。"""
import unittest
import petl

def test_casefold_target_and_rows_and_complement_keep_original_text():
    """Unicode归一化不是lower近似，目标同样应用key。@return None。"""
    table=[['name','id'],['Straße',1],['STRASSE',2],['Other',3]]
    assert list(petl.selecteq(table,'name','strasse',key=str.casefold))==[('name','id'),('Straße',1),('STRASSE',2)]
    assert list(petl.wrap(table).selecteq('name','STRASSE',complement=True,key=str.casefold))==[('name','id'),('Other',3)]
    assert list(petl.selecteq(table,'name','strasse'))==[('name','id')]

def test_none_falsey_key_and_callback_errors_are_explicit():
    """不猜None或数值的归一化，回调自己负责明确政策。@return None。"""
    class Key:
        """假值函数仍可作为归一化。"""
        def __bool__(self):return False
        def __call__(self,value):return '' if value is None else str(value)
    table=[['value'],[None],[''],[3]]
    assert list(petl.selecteq(table,'value','',key=Key()))==[('value',),(None,),('',)]
    with unittest.TestCase().assertRaises(TypeError):petl.selecteq(table,'value',3,key=False)

