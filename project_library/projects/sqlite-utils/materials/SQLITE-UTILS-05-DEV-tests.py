"Public regression tests for SQLITE-UTILS-05-DEV; the complete business contract is in materials/SQLITE-UTILS-05-DEV-contract.md."
import unittest
from sqlite_utils import recipes

def test_both_recipes_ignore_or_null_overflow_without_changing_defaults():
    "Verify both recipes ignore or null overflow without changing defaults."
    value='999999999999999999999-01-01'
    for function in (recipes.parsedate,recipes.parsedatetime):
        assert function(value,errors=recipes.IGNORE)==value
        assert function(value,errors=recipes.SET_NULL) is None
        with unittest.TestCase().assertRaises((OverflowError,ValueError)):function(value)

def test_normal_dates_parser_errors_empty_and_falsey_values_keep_policy():
    "Verify normal dates parser errors empty and falsey values keep policy."
    assert recipes.parsedate('2024-02-29')=='2024-02-29'
    assert recipes.parsedatetime('2024-02-29 13:45:00')=='2024-02-29T13:45:00'
    for function in (recipes.parsedate,recipes.parsedatetime):
        assert function('',errors=recipes.SET_NULL)=='' and function(None) is None
        assert function('not-a-date',errors=recipes.IGNORE)=='not-a-date'
        assert function('not-a-date',errors=recipes.SET_NULL) is None

