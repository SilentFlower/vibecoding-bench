"Public regression tests for NATSORT-01-DEV; the complete business contract is in materials/NATSORT-01-DEV-contract.md."
import contextlib
import io
from natsort.__main__ import main


def output(*args):
    "Support the public regression through output."
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):main(*args)
    return stream.getvalue().splitlines()


def test_exclude_adjacent_large_integers():
    "Verify exclude adjacent large integers."
    a=2**53
    assert output('--exclude',str(a),'item'+str(a),'item'+str(a+1))==['item'+str(a+1)]


def test_inclusive_range_preserves_exact_boundaries():
    "Verify inclusive range preserves exact boundaries."
    a=2**53
    assert output('--filter',str(a+1),str(a+2),*['x'+str(a+i) for i in range(3)])==['x'+str(a+1),'x'+str(a+2)]
    assert output('--filter','1.5','2.5','x1','x2','x3')==['x2']


def test_float_policy_stays_float():
    "Verify float policy stays float."
    assert output('--number-type','float','--filter','1.2','2.9','x3.0','x2.5','x1.5')==['x1.5','x2.5']

