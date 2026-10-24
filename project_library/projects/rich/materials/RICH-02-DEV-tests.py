"Public regression tests for RICH-02-DEV; the complete business contract is in materials/RICH-02-DEV-contract.md."
import json
import subprocess
import sys
from rich.traceback import Traceback


def test_cycle_is_extracted_once_under_hard_test_timeout():
    "Verify cycle is extracted once under hard test timeout."
    script="from rich.traceback import Traceback; a=ValueError('a'); b=TypeError('b'); a.__cause__=b; b.__cause__=a; result=Traceback.extract(type(a),a,None); print(len(result.stacks))"
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=2,check=True)
    assert result.stdout.strip()=='2'


def test_unhashable_shared_exception_and_per_object_notes():
    "Verify unhashable shared exception and per object notes."
    class UnhashableError(Exception):
        "Public regression fixture: UnhashableError."
        __hash__=None
    a=UnhashableError('same');b=UnhashableError('same');a.add_note('A');b.add_note('B');a.__cause__=b
    result=Traceback.extract(type(a),a,None)
    assert len(result.stacks)==2 and [stack.notes for stack in result.stacks]==[['A'],['B']]
    group=ExceptionGroup('group',[a,b,a]);trace=Traceback.extract(type(group),group,None)
    count=sum(len(child.stacks) for child in trace.stacks[0].exceptions)
    assert count==2

