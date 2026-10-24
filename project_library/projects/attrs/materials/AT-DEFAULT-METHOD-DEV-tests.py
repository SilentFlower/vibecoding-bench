"Public regression tests for AT-DEFAULT-METHOD-DEV; the complete business contract is in materials/AT-DEFAULT-METHOD-DEV-contract.md."
import attrs
import pytest

def test_subclass_override_is_used_only_in_the_explicit_mode():
    @attrs.define
    class Base:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        def _default(self):
            return 'base'
    @attrs.define
    class Child(Base):
        def _default(self):
            return 'child'
    assert Base().value == 'base' and Child().value == 'child'

def test_explicit_values_do_not_call_the_method():
    @attrs.define
    class Model:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        def _default(self):
            raise AssertionError('不应调用')
    assert Model(5).value == 5

def test_default_can_read_previously_initialized_fields():
    @attrs.define
    class Model:
        prefix: str
        value: str = attrs.field(default=attrs.Factory.from_method('_default'))
        def _default(self):
            return self.prefix + '-ready'
    assert Model('order').value == 'order-ready'

def test_invalid_names_and_missing_methods_fail_clearly():
    with pytest.raises(TypeError):
        attrs.Factory.from_method(3)
    with pytest.raises(ValueError):
        attrs.Factory.from_method('')
    @attrs.define
    class Model:
        value = attrs.field(default=attrs.Factory.from_method('_missing'))
    with pytest.raises(AttributeError):
        Model()

def test_static_and_class_methods_are_not_instance_defaults():
    @attrs.define
    class Static:
        value = attrs.field(default=attrs.Factory.from_method('_default'))
        @staticmethod
        def _default():
            return 1
    with pytest.raises(TypeError):
        Static()

def test_regular_factories_are_unchanged():
    @attrs.define
    class Model:
        value = attrs.field(factory=list)
    first, second = Model(), Model()
    first.value.append(1)
    assert second.value == []
