"Public regression tests for PYTHON-DATEUTIL-04-DEV; the complete business contract is in materials/PYTHON-DATEUTIL-04-DEV-contract.md."
from datetime import datetime
import unittest
from dateutil.parser import isoparse

def test_nonexistent_week53_is_rejected_in_basic_extended_and_default_day():
    "Verify nonexistent week53 is rejected in basic extended and default day."
    for source in ('2021-W53-1','2021W531','2021-W53','2021W53'):
        with unittest.TestCase().assertRaises(ValueError):isoparse(source)

def test_valid_week53_and_gregorian_year_boundary_remain_valid():
    "Verify valid week53 and gregorian year boundary remain valid."
    assert isoparse('2020-W53-7')==datetime(2021,1,3)
    assert isoparse('2015-W53-1')==datetime(2015,12,28)
    assert isoparse('2020-W01-1')==datetime(2019,12,30)
    assert isoparse('2024-W01')==datetime(2024,1,1)

