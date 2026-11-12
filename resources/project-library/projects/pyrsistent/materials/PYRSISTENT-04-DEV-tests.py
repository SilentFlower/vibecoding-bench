"Public regression tests for PYRSISTENT-04-DEV; the complete business contract is in materials/PYRSISTENT-04-DEV-contract.md."
from pyrsistent import PRecord,CheckedPMap,CheckedPVector,CheckedPSet,field


class Item(PRecord):
    "Public regression fixture: Item."
    quantity=field(type=int,serializer=lambda format,value:str(format)+':'+str(value))


class Items(CheckedPMap):
    "Public regression fixture: Items."
    __key_type__=str
    __value_type__=Item


def test_nested_map_and_vector_receive_the_same_format():
    "Verify nested map and vector receive the same format."
    class Sequence(CheckedPVector):
        "Public regression fixture: Sequence."
        __type__=Item
    item=Item(quantity=2)
    assert item.serialize('json')=={'quantity':'json:2'}
    assert Items({'a':item}).serialize('json')=={'a':{'quantity':'json:2'}}
    assert Sequence([item]).serialize('json')==[{'quantity':'json:2'}]


def test_custom_container_serializer_retains_authority_and_default():
    "Verify custom container serializer retains authority and default."
    class Custom(Items):
        "Public regression fixture: Custom."
        def __serializer__(self,format,key,value):
            "Support the public regression through __serializer__."
            return key,str(format)+':custom'
    item=Item(quantity=3)
    assert Custom({'a':item}).serialize('wire')=={'a':'wire:custom'}
    assert Items({'a':item}).serialize()=={'a':{'quantity':'None:3'}}

