"""一次性错误上下文拥有与list输入完全相同的绝对父链。"""
from jsonschema.exceptions import ValidationError,SchemaError

def test_generator_children_gain_parent_and_absolute_paths():
    """子错误身份保留，实例及schema绝对路径都包含真实父路径。@return None。"""
    child=ValidationError('child',path=['leaf'],schema_path=['type'])
    parent=ValidationError('parent',path=['record'],schema_path=['properties','record'],context=(value for value in [child]))
    assert parent.context==[child] and parent.context[0] is child and child.parent is parent
    assert list(child.absolute_path)==['record','leaf'] and list(child.absolute_schema_path)==['properties','record','type']

def test_one_shot_iterator_not_reiterated_and_deep_nesting_works():
    """禁止二次__iter__的真实输入也只消费一次，深层父链完整。@return None。"""
    class Once:
        """精确检测重复消费的上下文源。"""
        def __init__(self,child):self.child=child;self.used=False
        def __iter__(self):
            assert not self.used;self.used=True;yield self.child
    leaf=ValidationError('leaf',path=[0]);middle=ValidationError('middle',path=['items'],context=Once(leaf))
    outer=ValidationError('outer',path=['root'],context=Once(middle))
    assert list(leaf.absolute_path)==['root','items',0] and leaf.parent is middle and middle.parent is outer

def test_schema_errors_conversion_empty_tuple_and_list_keep_identity():
    """SchemaError及转换入口同样挂父链，空上下文和旧容器保持。@return None。"""
    child=SchemaError('bad',path=['part']);parent=SchemaError('schema',path=['root'],context=iter([child]))
    assert child.parent is parent and list(child.absolute_path)==['root','part']
    converted=SchemaError.create_from(parent);assert converted.context[0] is child and child.parent is converted
    assert ValidationError('empty',context=iter(())).context==[]
    leaf=ValidationError('old');container=ValidationError('p',context=(leaf,));assert leaf.parent is container
