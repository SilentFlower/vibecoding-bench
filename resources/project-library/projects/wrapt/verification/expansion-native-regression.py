"""冻结Wrapt完整回归仅规范八个指定子项字段的repr地址。"""
import re
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

spec=spec_from_file_location('frozen_wrapt_control',Path(__file__).with_name('native_regression.py'))
control=module_from_spec(spec);spec.loader.exec_module(control)
original=control._subtest_results
targets={('tests/core/test_auto_object_proxy.py::TestAutoObjectProxy::test_descriptor_optional_owner', 1, 'call', 'descriptor'): '<function TestAutoObjectProxy.test_descriptor_optional_owner.<locals>.method at <address>>', ('tests/core/test_auto_object_proxy.py::TestAutoObjectProxy::test_descriptor_optional_owner', 2, 'call', 'descriptor'): '<property object at <address>>', ('tests/core/test_lazy_object_proxy.py::TestLazyObjectProxy::test_descriptor_optional_owner', 1, 'call', 'descriptor'): '<function TestLazyObjectProxy.test_descriptor_optional_owner.<locals>.method at <address>>', ('tests/core/test_lazy_object_proxy.py::TestLazyObjectProxy::test_descriptor_optional_owner', 2, 'call', 'descriptor'): '<property object at <address>>', ('tests/core/test_weak_function_proxy.py::TestWeakFunctionProxy::test_decorated_descriptors', 3, 'call', 'target'): '<test_weak_function_proxy.TestWeakFunctionProxy.test_decorated_descriptors.<locals>.Class object at <address>>', ('tests/core/test_weak_function_proxy.py::TestWeakFunctionProxy::test_decorated_descriptors', 4, 'call', 'target'): '<test_weak_function_proxy.TestWeakFunctionProxy.test_decorated_descriptors.<locals>.Class object at <address>>', ('tests/core/test_weak_function_proxy.py::TestWeakFunctionProxy::test_decorated_descriptors', 7, 'call', 'target'): '<test_weak_function_proxy.TestWeakFunctionProxy.test_decorated_descriptors.<locals>.Subclass object at <address>>', ('tests/core/test_weak_function_proxy.py::TestWeakFunctionProxy::test_decorated_descriptors', 8, 'call', 'target'): '<test_weak_function_proxy.TestWeakFunctionProxy.test_decorated_descriptors.<locals>.Subclass object at <address>>'}
address=re.compile(r'(?<= at )0x[0-9a-fA-F]+(?=>)')

def normalized(reports,node_ids):
    """仅改已知字段的地址并核其它展示不变。@param reports 原报告。@param node_ids 原节点。@return 全部同序真实子项。"""
    result=original(reports,node_ids);changed=0
    for item in result:
        for key,value in item['context']['kwargs'].items():
            scope=(item['parent_nodeid'],item['ordinal'],item['when'],key)
            if scope in targets:
                replacement=address.sub('<address>',value)
                if replacement!=targets[scope]:raise ValueError('冻结对象展示除地址外发生变化')
                item['context']['kwargs'][key]=replacement;changed+=1
    if changed!=len(targets):raise ValueError('冻结对象子项集合变化')
    return result

control._subtest_results=normalized
if __name__=='__main__':control.main()
