"Public regression tests for AN-SLOTS-DEV; the complete business contract is in materials/AN-SLOTS-DEV-contract.md."
import pytest
from anytree import LightNodeMixin, AnyNode
from anytree.exporter import DictExporter
from anytree.importer import DictImporter

class Slim(LightNodeMixin):
    __slots__ = ('name', 'quantity')
    def __init__(self, name, quantity, parent=None):
        self.name, self.quantity, self.parent = name, quantity, parent

def fields(node):
    return {'name': node.name, 'quantity': node.quantity}

def test_slots_nodes_export_with_explicit_fields():
    root = Slim('r', 1)
    Slim('c', 2, parent=root)
    assert DictExporter(attribute_provider=fields).export(root) == {'name':'r', 'quantity':1,
        'children':[{'name':'c', 'quantity':2}]}

def test_provider_results_still_use_attribute_filtering():
    result = DictExporter(attribute_provider=fields, attriter=lambda pairs: [(k,v) for k,v in pairs if k == 'name']).export(Slim('r', 1))
    assert result == {'name':'r'}

def test_structural_fields_cannot_leak_or_replace_real_children():
    root = Slim('r', 1)
    data = DictExporter(attribute_provider=lambda node: {'name':node.name, 'parent':'private',
        '_LightNodeMixin__children':'private', 'children':'fake'}).export(root)
    assert data == {'name':'r'}

def test_depth_and_importer_roundtrip_are_preserved():
    root = Slim('r', 1)
    Slim('c', 2, parent=root)
    assert DictExporter(attribute_provider=fields, maxlevel=1).export(root) == {'name':'r', 'quantity':1}
    restored = DictImporter().import_(DictExporter(attribute_provider=fields).export(root))
    assert restored.children[0].quantity == 2

def test_invalid_provider_and_errors_are_explicit():
    with pytest.raises(TypeError):
        DictExporter(attribute_provider=3)
    with pytest.raises(ZeroDivisionError):
        DictExporter(attribute_provider=lambda node: 1/0).export(Slim('r', 1))

def test_default_dict_exporter_keeps_normal_node_behavior():
    assert DictExporter().export(AnyNode(name='x', quantity=4)) == {'name':'x', 'quantity':4}
