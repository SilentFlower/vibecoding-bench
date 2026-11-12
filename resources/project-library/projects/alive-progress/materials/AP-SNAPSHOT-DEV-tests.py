"Public regression tests for AP-SNAPSHOT-DEV; the complete business contract is in materials/AP-SNAPSHOT-DEV-contract.md."
from io import StringIO
import pytest
from alive_progress import alive_bar

def test_actual_count_skipped_processed_and_frozen_values():
    with alive_bar(10,disable=True) as bar:
        bar(2);first=bar.snapshot();bar(3,skipped=True);second=bar.snapshot()
        assert first.count==2 and first.processed==2 and second.count==5 and second.processed==2 and second.percent==0.5
        with pytest.raises((AttributeError,TypeError)):
            first.count=9

def test_unknown_and_manual_modes_have_explicit_raw_meaning():
    with alive_bar(disable=True) as bar:
        bar(3);snapshot=bar.snapshot();assert snapshot.count==3 and snapshot.total is None and snapshot.percent is None
    with alive_bar(10,manual=True,disable=True) as bar:
        bar(0.4);snapshot=bar.snapshot();assert snapshot.manual and snapshot.count==4 and snapshot.percent==0.4

def test_snapshot_does_not_write_and_remains_available_after_finish():
    output=StringIO()
    with alive_bar(2,file=output,force_tty=False,enrich_print=False,receipt=False) as bar:
        bar();before=output.getvalue();snapshot=bar.snapshot();assert output.getvalue()==before and snapshot.active
    assert not bar.snapshot().active and bar.snapshot().count==1

def test_earlier_snapshot_does_not_change_with_later_progress():
    with alive_bar(3,disable=True) as bar:
        first=bar.snapshot();bar(2);second=bar.snapshot()
        assert first.count==0 and second.count==2 and first is not second
