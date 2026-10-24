"Public regression tests for PYTHON-DATEUTIL-06-DEV; the complete business contract is in materials/PYTHON-DATEUTIL-06-DEV-contract.md."
import copy
import pickle
from datetime import datetime
from dateutil.rrule import rrule,rruleset,DAILY

def test_cached_rule_partial_complete_pickle_and_deepcopy():
    "Verify cached rule partial complete pickle and deepcopy."
    for complete in (False,True):
        rule=rrule(DAILY,dtstart=datetime(2024,1,1),count=4,cache=True)
        if complete:list(rule)
        else:next(iter(rule))
        for restored in (pickle.loads(pickle.dumps(rule)),copy.deepcopy(rule)):
            assert list(restored)==list(rule) and restored._cache is not None
            assert restored._cache_lock is not rule._cache_lock

def test_cached_ruleset_include_exclude_and_uncached_old_state():
    "Verify cached ruleset include exclude and uncached old state."
    values=rruleset(cache=True);values.rrule(rrule(DAILY,dtstart=datetime(2024,1,1),count=3))
    values.exdate(datetime(2024,1,2));values.rdate(datetime(2024,1,6))
    restored=pickle.loads(pickle.dumps(values))
    assert list(restored)==[datetime(2024,1,1),datetime(2024,1,3),datetime(2024,1,6)]
    original=rrule(DAILY,dtstart=datetime(2024,2,1),count=1)
    legacy=object.__new__(rrule);legacy.__setstate__(dict(original.__dict__))
    assert list(legacy)==list(original) and legacy._cache is None

