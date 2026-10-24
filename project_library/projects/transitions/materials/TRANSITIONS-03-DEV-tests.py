"""配置可供生成器和多个流程重复使用，不能pop调用方models。"""
from types import MappingProxyType
from transitions.extensions.markup import MarkupMachine,HierarchicalMarkupMachine
from transitions.experimental.utils import generate_base_model

def test_reusing_markup_preserves_models_and_nested_configuration():
    """models空列表也必须原样保留，嵌套状态不被消费。@return None。"""
    config={'states':['a','b'],'initial':'a','auto_transitions':False,'transitions':[['go','a','b']],'models':[]}
    before=repr(config)
    first=MarkupMachine(markup=config);second=MarkupMachine(markup=MappingProxyType(config))
    assert repr(config)==before and config['models']==[]
    assert first.states.keys()==second.states.keys()
    first._markup['initial']='b';assert config['initial']=='a'

def test_code_generation_does_not_consume_models_or_copy_callbacks():
    """同一配置重复生成结果一致，不深拷贝不透明对象。@return None。"""
    config={'states':['a','b'],'initial':'a','auto_transitions':False,'transitions':[['go','a','b']],'models':[]}
    first=generate_base_model(config);second=generate_base_model(config)
    assert first==second and config['models']==[] and 'def go(' in first
    from transitions._config import clone_config
    class Callback:
        """不允许任意对象复制。"""
        def __deepcopy__(self,memo):raise AssertionError('opaque')
    callback=Callback();shared=[callback];copied=clone_config({'a':shared,'b':shared})
    assert copied['a'] is copied['b'] and copied['a'] is not shared and copied['a'][0] is callback

