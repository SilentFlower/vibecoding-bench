"Public regression tests for TQDM-05-DEV; the complete business contract is in materials/TQDM-05-DEV-contract.md."
import threading
import unittest
from tqdm import tqdm
from tqdm.contrib.concurrent import ensure_lock,thread_map


def test_exception_and_nested_lock_context_restore_exact_identity():
    "Verify exception and nested lock context restore exact identity."
    class Local(tqdm):
        "Public regression fixture: Local."
    original=threading.RLock();temporary=threading.RLock();inner=threading.RLock();Local.set_lock(original)
    with unittest.TestCase().assertRaises(ValueError):
        with ensure_lock(Local,lock=temporary):
            assert Local.get_lock() is temporary
            with ensure_lock(Local,lock=inner):assert Local.get_lock() is inner
            assert Local.get_lock() is temporary
            raise ValueError('worker failed')
    assert Local.get_lock() is original


def test_inherited_absent_and_real_worker_failure_cleanup():
    "Verify inherited absent and real worker failure cleanup."
    class Local(tqdm):
        "Public regression fixture: Local."
    parent=tqdm.get_lock();assert Local.get_lock() is parent
    assert '_lock' not in Local.__dict__
    with unittest.TestCase().assertRaises(RuntimeError):
        with ensure_lock(Local,lock=threading.RLock()):raise RuntimeError('body')
    assert '_lock' not in Local.__dict__ and Local.get_lock() is parent
    def broken(value):
        "Support the public regression through broken."
        raise RuntimeError('worker')
    with unittest.TestCase().assertRaises(RuntimeError):thread_map(broken,[1],max_workers=1,tqdm_class=Local,disable=True)
    assert '_lock' not in Local.__dict__ and Local.get_lock() is parent

