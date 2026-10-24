"""缺字段与真实None不能被drop_missing混淆。"""
from structlog.processors import KeyValueRenderer,LogfmtRenderer

def test_both_renderers_keep_explicit_none_drop_only_absent():
    """无序/排序两条共享路径都保空值。@return None。"""
    for sorted_keys in (False,True):
        values={'present':None,'false':False,'zero':0,'empty':''}
        text=KeyValueRenderer(key_order=['missing','present','false','zero','empty'],sort_keys=sorted_keys,drop_missing=True)(None,'info',dict(values))
        assert 'present=None' in text and 'missing=' not in text and 'false=False' in text and 'zero=0' in text
        text=LogfmtRenderer(key_order=['missing','present'],sort_keys=sorted_keys,drop_missing=True)(None,'info',dict(values))
        assert 'present=' in text and 'missing=' not in text

def test_default_missing_and_ordered_consumption_remain_compatible():
    """默认缺项仍渲染None，原有字典消费方式保持。@return None。"""
    values={'a':None,'b':2}
    result=KeyValueRenderer(key_order=['a','absent'],drop_missing=False)(None,'info',values)
    assert result=='a=None absent=None b=2' and values=={'b':2}

