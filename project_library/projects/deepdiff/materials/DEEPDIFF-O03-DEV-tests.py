"""固定偏移时区比较及Hash不再把不同对象误判为相同空属性。"""
from datetime import timezone,timedelta,tzinfo
from deepdiff import DeepDiff,DeepHash

def test_actual_offsets_and_same_offset_different_name():
    """同偏移名称不参与相等，偏移不同会报告值差异。@return None。"""
    a=timezone(timedelta(hours=1),'name-a');b=timezone(timedelta(hours=1),'name-b')
    assert DeepDiff(a,b)=={}
    assert 'values_changed' in DeepDiff(timezone.utc,a)
    assert DeepHash(a)[a]==DeepHash(b)[b]

def test_negative_fractional_and_nested_hash_pairing():
    """负偏移、非整小时及无序容器都区分实际偏移。@return None。"""
    a=timezone(timedelta(hours=-3,minutes=-30));b=timezone(timedelta(hours=5,minutes=45))
    assert DeepDiff({'zone':a},{'zone':b})
    assert DeepHash(a)[a]!=DeepHash(b)[b]
    assert DeepDiff([a],[b],ignore_order=True)

def test_identity_zero_and_dynamic_tzinfo_type_rules():
    """不同tzinfo类继续按原类型规则，不扩大成动态时区承诺。@return None。"""
    assert DeepDiff(timezone.utc,timezone(timedelta(0),'zero'))=={}
    class Dynamic(tzinfo):
        """不同的动态时区类型。"""
        def utcoffset(self,dt):return timedelta(0)
    assert 'type_changes' in DeepDiff(timezone.utc,Dynamic())
