"Public regression tests for AR-MATCH-DEV; the complete business contract is in materials/AR-MATCH-DEV-contract.md."
from dataclasses import FrozenInstanceError
from datetime import datetime
import pytest
from arrow.parser import DateTimeParser, ParserError

def test_report_preserves_original_fragment_and_surrounding_text():
    text = 'prefix 2026-01-02 suffix'
    report = DateTimeParser().parse_match(text, 'YYYY-MM-DD')
    assert report.value == datetime(2026,1,2) and report.span == (7,17)
    assert report.matched == '2026-01-02' and report.prefix + report.matched + report.suffix == text

def test_unicode_prefix_uses_character_offsets_not_byte_offsets():
    text = '记录： 2026-01-02 完成'
    report = DateTimeParser().parse_match(text, 'YYYY-MM-DD')
    assert text[slice(*report.span)] == report.matched and report.span[0] == 4

def test_normalized_whitespace_maps_back_to_exact_raw_text():
    text = 'log 2026-01-02		 03:04 done'
    report = DateTimeParser().parse_match(text, 'YYYY-MM-DD HH:mm', True)
    assert report.matched == '2026-01-02		 03:04'
    assert report.span[1] - report.span[0] > report.normalized_span[1] - report.normalized_span[0]

def test_earliest_valid_match_wins_across_format_order():
    report = DateTimeParser().parse_match('2026/03/04 then 2026-05-06', ['YYYY-MM-DD','YYYY/MM/DD'])
    assert report.format == 'YYYY/MM/DD' and report.value.month == 3

def test_invalid_calendar_matches_are_skipped_and_no_match_is_explicit():
    assert DateTimeParser().parse_match('2026-02-30 then 2026-03-02', 'YYYY-MM-DD').value.month == 3
    with pytest.raises(ParserError):
        DateTimeParser().parse_match('no dates here', 'YYYY-MM-DD')

def test_report_is_immutable_and_original_parse_stays_datetime():
    parser = DateTimeParser()
    report = parser.parse_match('2026-01-02', 'YYYY-MM-DD')
    with pytest.raises(FrozenInstanceError):
        report.span = (0,1)
    assert isinstance(parser.parse('2026-01-02', 'YYYY-MM-DD'), datetime)
