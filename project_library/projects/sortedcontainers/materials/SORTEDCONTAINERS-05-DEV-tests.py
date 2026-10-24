"Public regression tests for SORTEDCONTAINERS-05-DEV; the complete business contract is in materials/SORTEDCONTAINERS-05-DEV-contract.md."
from operator import neg
from sortedcontainers import SortedList,SortedSet,SortedDict

def test_halfopen_ranges_all_container_families_and_remaining_indexes():
    "Verify halfopen ranges all container families and remaining indexes."
    for source in (SortedList([1,2,3,4,5]),SortedSet([1,2,3,4,5]),SortedDict({x:str(x) for x in range(1,6)})):
        result=source.pop_range(2,4,inclusive=(True,False))
        assert result==([(2,'2'),(3,'3')] if isinstance(source,dict) else [2,3])
        assert list(source)==[1,4,5];source._check()

def test_duplicates_unbounded_empty_and_reverse_key():
    "Verify duplicates unbounded empty and reverse key."
    source=SortedList([1,2,2,3,4]);source._reset(4)
    assert source.pop_range(2,3,reverse=True)==[3,2,2] and list(source)==[1,4]
    assert source.pop_range(8,2)==[];source._check()
    reverse=SortedList([1,2,3,4],key=neg)
    assert reverse.pop_range(4,2,inclusive=(False,True))==[3,2] and list(reverse)==[4,1]
    assert reverse.pop_range()==[4,1] and len(reverse)==0;reverse._check()

