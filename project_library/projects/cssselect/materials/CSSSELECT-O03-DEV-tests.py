"""LRU命中、配置隔离和清空均通过实际翻译验证。"""
import pytest
import cssselect

def test_lru_uses_access_order_and_capacity():
    """重读保护热项，第三项淘汰最久未访问项。@return None。"""
    from cssselect.cache import SelectorCache
    c=SelectorCache(2);c.translate('a');c.translate('b');c.translate('a');c.translate('c')
    assert c.stats()=={'size':2,'capacity':2,'hits':1,'misses':3,'evictions':1}
    c.translate('b');assert c.stats()['misses']==4 and c.stats()['evictions']==2

def test_configuration_and_failed_result_isolation():
    """HTML/XML、XHTML和prefix各自独立，失败不缓存。@return None。"""
    from cssselect.cache import SelectorCache
    c=SelectorCache(9)
    assert c.translate('DIV')!=c.translate('DIV',mode='html')
    assert c.translate('DIV',mode='html',xhtml=True)!=c.translate('DIV',mode='html')
    assert c.translate('p',prefix='self::')=='self::p'
    for _ in range(2):
        with pytest.raises(cssselect.ExpressionError):c.translate(':unknown')
    assert c.stats()['size']==4 and c.stats()['misses']==6

def test_clear_and_independent_instances():
    """清空和统计副本不会影响其他实例。@return None。"""
    from cssselect.cache import SelectorCache
    c=SelectorCache(1);d=SelectorCache(1);c.translate('p');c.clear()
    assert c.stats()['size']==0 and c.stats()['misses']==1 and d.stats()['misses']==0
    c.stats()['misses']=999;c.clear(reset_stats=True);assert c.stats()['misses']==0
    with pytest.raises(ValueError):SelectorCache(True)
