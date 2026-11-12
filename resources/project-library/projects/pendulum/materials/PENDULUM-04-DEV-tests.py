"Public regression tests for PENDULUM-04-DEV; the complete business contract is in materials/PENDULUM-04-DEV-contract.md."
import copy
import pickle
import pendulum
from pendulum.duration import Duration,AbsoluteDuration

def test_calendar_components_survive_protocols_copy_and_anchor_addition():
    "Verify calendar components survive protocols copy and anchor addition."
    value=Duration(years=1,months=2,weeks=1,days=3,hours=4,microseconds=5)
    anchor=pendulum.datetime(2024,1,31)
    restored=[copy.copy(value),copy.deepcopy(value)]+[pickle.loads(pickle.dumps(value,protocol=n)) for n in range(pickle.HIGHEST_PROTOCOL+1)]
    for result in restored:
        assert result._signature==value._signature and result.years==1 and result.months==2
        assert anchor+result==anchor+value

def test_absolute_duration_and_zero_preserve_concrete_type_and_behavior():
    "Verify absolute duration and zero preserve concrete type and behavior."
    for value in (AbsoluteDuration(years=2,months=3,days=-2,hours=-1),Duration(),Duration(days=-1,microseconds=7)):
        result=pickle.loads(pickle.dumps(value))
        assert type(result) is type(value) and result==value
        assert result.years==value.years and result.months==value.months and result.invert==value.invert

