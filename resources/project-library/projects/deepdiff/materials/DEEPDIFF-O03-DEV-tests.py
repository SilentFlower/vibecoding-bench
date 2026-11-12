"Public regression tests for DEEPDIFF-O03-DEV; the complete business contract is in materials/DEEPDIFF-O03-DEV-contract.md."
from datetime import timezone,timedelta,tzinfo
from deepdiff import DeepDiff,DeepHash

def test_actual_offsets_and_same_offset_different_name():
    "Verify actual offsets and same offset different name."
    a=timezone(timedelta(hours=1),'name-a');b=timezone(timedelta(hours=1),'name-b')
    assert DeepDiff(a,b)=={}
    assert 'values_changed' in DeepDiff(timezone.utc,a)
    assert DeepHash(a)[a]==DeepHash(b)[b]

def test_negative_fractional_and_nested_hash_pairing():
    "Verify negative fractional and nested hash pairing."
    a=timezone(timedelta(hours=-3,minutes=-30));b=timezone(timedelta(hours=5,minutes=45))
    assert DeepDiff({'zone':a},{'zone':b})
    assert DeepHash(a)[a]!=DeepHash(b)[b]
    assert DeepDiff([a],[b],ignore_order=True)

def test_identity_zero_and_dynamic_tzinfo_type_rules():
    "Verify identity zero and dynamic tzinfo type rules."
    assert DeepDiff(timezone.utc,timezone(timedelta(0),'zero'))=={}
    class Dynamic(tzinfo):
        "Public regression fixture: Dynamic."
        def utcoffset(self,dt):return timedelta(0)
    assert 'type_changes' in DeepDiff(timezone.utc,Dynamic())
