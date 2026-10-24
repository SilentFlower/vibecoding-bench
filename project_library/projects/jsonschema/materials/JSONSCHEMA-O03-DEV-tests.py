"Public regression tests for JSONSCHEMA-O03-DEV; the complete business contract is in materials/JSONSCHEMA-O03-DEV-contract.md."
from jsonschema.exceptions import ValidationError,SchemaError

def test_generator_children_gain_parent_and_absolute_paths():
    "Verify generator children gain parent and absolute paths."
    child=ValidationError('child',path=['leaf'],schema_path=['type'])
    parent=ValidationError('parent',path=['record'],schema_path=['properties','record'],context=(value for value in [child]))
    assert parent.context==[child] and parent.context[0] is child and child.parent is parent
    assert list(child.absolute_path)==['record','leaf'] and list(child.absolute_schema_path)==['properties','record','type']

def test_one_shot_iterator_not_reiterated_and_deep_nesting_works():
    "Verify one shot iterator not reiterated and deep nesting works."
    class Once:
        "Public regression fixture: Once."
        def __init__(self,child):self.child=child;self.used=False
        def __iter__(self):
            assert not self.used;self.used=True;yield self.child
    leaf=ValidationError('leaf',path=[0]);middle=ValidationError('middle',path=['items'],context=Once(leaf))
    outer=ValidationError('outer',path=['root'],context=Once(middle))
    assert list(leaf.absolute_path)==['root','items',0] and leaf.parent is middle and middle.parent is outer

def test_schema_errors_conversion_empty_tuple_and_list_keep_identity():
    "Verify schema errors conversion empty tuple and list keep identity."
    child=SchemaError('bad',path=['part']);parent=SchemaError('schema',path=['root'],context=iter([child]))
    assert child.parent is parent and list(child.absolute_path)==['root','part']
    converted=SchemaError.create_from(parent);assert converted.context[0] is child and child.parent is converted
    assert ValidationError('empty',context=iter(())).context==[]
    leaf=ValidationError('old');container=ValidationError('p',context=(leaf,));assert leaf.parent is container
