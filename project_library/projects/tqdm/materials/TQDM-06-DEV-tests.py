"""环境布尔False不是非空字符串True，显式调用仍有优先级。"""
import os
import unittest
from unittest.mock import patch
from tqdm.utils import envwrap


def test_bool_default_annotation_and_explicit_type_fallback():
    """三种真实类型来源都按明确字面量解析。@return None。"""
    for raw,expected in [('False',False),('0',False),('off',False),('TRUE',True),('1',True),('yes',True)]:
        with patch.dict(os.environ,{'BUSINESS_FLAG':raw}):
            @envwrap('business')
            def default(flag=True):return flag
            @envwrap('business')
            def annotated(flag:bool=None):return flag
            @envwrap('business',types={'flag':bool})
            def fallback(flag=None):return flag
            assert default() is annotated() is fallback() is expected
            assert default(flag=not expected) is not expected


def test_unknown_boolean_rejects_and_other_types_keep_conversion():
    """未知布尔不能静默开启，非布尔原推断不变。@return None。"""
    with patch.dict(os.environ,{'BUSINESS_FLAG':'maybe'}):
        with unittest.TestCase().assertRaises(ValueError):
            envwrap('business')(lambda flag=False:flag)
    with patch.dict(os.environ,{'BUSINESS_NUMBER':'42','BUSINESS_NAME':'False'}):
        @envwrap('business')
        def ordinary(number=1,name='text'):return number,name
        assert ordinary()==(42,'False')

