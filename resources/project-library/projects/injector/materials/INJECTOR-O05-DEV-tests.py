"Public regression tests for INJECTOR-O05-DEV; the complete business contract is in materials/INJECTOR-O05-DEV-contract.md."
from injector import Injector,SingletonScope,ThreadLocalScope
import threading

def test_single_target_invalidation_preserves_other_and_bindings():
    "Verify single target invalidation preserves other and bindings."
    class A:
        "Public regression fixture: A."
    class B:
        "Public regression fixture: B."
    container=Injector(lambda b:(b.bind(A,scope=SingletonScope),b.bind(B,scope=SingletonScope)))
    first,other=container.get(A),container.get(B);scope=container.get(SingletonScope)
    assert scope.evict(A) is True and scope.evict(A) is False
    assert container.get(A) is not first and container.get(B) is other
    assert container.binder.has_explicit_binding_for(A)

def test_singleton_clear_count_and_old_references_not_closed():
    "Verify singleton clear count and old references not closed."
    class Service:
        "Public regression fixture: Service."
        def __init__(self):self.closed=False
        def close(self):self.closed=True
    container=Injector(lambda b:b.bind(Service,scope=SingletonScope));scope=container.get(SingletonScope);value=container.get(Service)
    count=scope.clear();assert count>=1 and not value.closed and container.get(Service) is not value
    scope.clear();assert scope.clear()==0

def test_threadlocal_evict_clear_do_not_cross_thread():
    "Verify threadlocal evict clear do not cross thread."
    class Item:
        "Public regression fixture: Item."
    container=Injector(lambda b:b.bind(Item,scope=ThreadLocalScope));scope=container.get(ThreadLocalScope)
    first=container.get(Item);ready=threading.Event();release=threading.Event();result=[]
    def worker():
        original=container.get(Item);ready.set();release.wait();result.append(container.get(Item) is original)
    thread=threading.Thread(target=worker);thread.start();ready.wait()
    assert scope.evict(Item) and container.get(Item) is not first
    assert scope.clear()==1;release.set();thread.join();assert result==[True]
