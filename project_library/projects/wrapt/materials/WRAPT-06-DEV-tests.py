"""定点失效必须真正保留其他业务键，不能内部全清。"""
from wrapt.canonical_cache import canonical_cache

def test_one_canonical_key_invalidates_without_touching_other_or_stats():
    """管理操作与读取复用完全相同的默认值绑定。@return None。"""
    calls=[]
    @canonical_cache()
    def value(x,scale=2):calls.append(x);return {'value':x*scale}
    first=value(1);other=value(2);value(2);before=value.cache_info()
    assert value.cache_invalidate(x=1,scale=2) is True
    assert value.cache_invalidate(1) is False
    assert value(2) is other and value(1) is not first and calls==[1,2,1]
    assert value.cache_info().hits==before.hits+1

def test_custom_keys_method_instance_isolation_and_missing_invalidation():
    """同名方法不同self保持身份；自定义ID失效按策略精确匹配。@return None。"""
    class Item:
        @canonical_cache()
        def value(self,x=1):return object()
    a=Item();b=Item();first=a.value();second=b.value()
    assert Item.value.cache_invalidate(a,x=1) and b.value() is second and a.value() is not first
    @canonical_cache(key_func=lambda bound:bound.arguments['record']['id'])
    def business(record):return object()
    first=business({'id':3})
    assert business.cache_invalidate({'id':3,'extra':4}) and business({'id':3}) is not first

