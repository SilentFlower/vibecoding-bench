"Public regression tests for PYTHON-DATEUTIL-05-DEV; the complete business contract is in materials/PYTHON-DATEUTIL-05-DEV-contract.md."
from datetime import datetime,timedelta
from io import StringIO
import unittest
from dateutil.tz import tzical

BASE='BEGIN:VTIMEZONE\nTZID:Office\n{outer}BEGIN:STANDARD\nDTSTART:20200101T000000\nTZOFFSETFROM:+0300\nTZOFFSETTO:+0300\n{inner}END:STANDARD\nEND:VTIMEZONE'

def test_x_extensions_in_both_component_levels_do_not_change_offsets():
    "Verify x extensions in both component levels do not change offsets."
    for outer,inner in (('',''),('X-LIC-LOCATION:Europe/Office\n','X-CUSTOM;LANG=en:a\nx-custom:b\n')):
        zone=tzical(StringIO(BASE.format(outer=outer,inner=inner))).get('Office')
        assert datetime(2024,6,1,tzinfo=zone).utcoffset()==timedelta(hours=3)

def test_unknown_standard_and_required_field_errors_remain():
    "Verify unknown standard and required field errors remain."
    text=BASE.format(outer='UNKNOWN:value\n',inner='')
    with unittest.TestCase().assertRaises(ValueError):tzical(StringIO(text))
    text=BASE.format(outer='X-HINT:data\n',inner='').replace('TZID:Office\n','')
    with unittest.TestCase().assertRaises(ValueError):tzical(StringIO(text))

