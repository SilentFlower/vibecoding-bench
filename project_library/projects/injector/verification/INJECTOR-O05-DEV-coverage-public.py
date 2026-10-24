"""失效真实作用域缓存，绑定和其他缓存身份保持。"""
from injector import Injector,SingletonScope,ThreadLocalScope
import threading

def test_single_target_invalidation_preserves_other_and_bindings():
    """下次get重建目标，无关singleton及旧引用仍有效。@return None。"""
    class A:
        """首个服务。"""
    class B:
        """无关服务。"""
    container=Injector(lambda b:(b.bind(A,scope=SingletonScope),b.bind(B,scope=SingletonScope)))
    first,other=container.get(A),container.get(B);scope=container.get(SingletonScope)
    assert scope.evict(A) is True and scope.evict(A) is False
    assert container.get(A) is not first and container.get(B) is other
    assert container.binder.has_explicit_binding_for(A)

def test_singleton_clear_count_and_old_references_not_closed():
    """clear只移除缓存Provider，不伪装销毁外部业务实例。@return None。"""
    class Service:
        """带显式close的业务对象。"""
        def __init__(self):self.closed=False
        def close(self):self.closed=True
    container=Injector(lambda b:b.bind(Service,scope=SingletonScope));scope=container.get(SingletonScope);value=container.get(Service)
    count=scope.clear();assert count>=1 and not value.closed and container.get(Service) is not value
    scope.clear();assert scope.clear()==0

def test_threadlocal_evict_clear_do_not_cross_thread():
    """线程各自失效，另一线程对象保持原身份。@return None。"""
    class Item:
        """线程服务。"""
    container=Injector(lambda b:b.bind(Item,scope=ThreadLocalScope));scope=container.get(ThreadLocalScope)
    first=container.get(Item);ready=threading.Event();release=threading.Event();result=[]
    def worker():
        original=container.get(Item);ready.set();release.wait();result.append(container.get(Item) is original)
    thread=threading.Thread(target=worker);thread.start();ready.wait()
    assert scope.evict(Item) and container.get(Item) is not first
    assert scope.clear()==1;release.set();thread.join();assert result==[True]
