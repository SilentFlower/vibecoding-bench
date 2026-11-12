"""核真实attrs候选的数据转换、对象归属和发布边界。"""
import json
import os
from pathlib import Path
import sys

import attr
import attrs


def main() -> None:
    """只用合成对象核冻结业务事实，不修改候选。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(attr.__file__).resolve() == root / 'library/src/attr/__init__.py'
        and Path(attrs.__file__).resolve() == root / 'library/src/attrs/__init__.py'}
    task = sys.argv[1]
    if task == 'AT-U01':
        @attrs.define
        class Annotated:
            """仅有注解的合成输入。"""
            count: int

        @attrs.define
        class Converted:
            """显式声明转换和验证的合成输入。"""
            count: int = attrs.field(converter=int, validator=attrs.validators.instance_of(int))

        plain, converted = Annotated('7'), Converted('7')
        converted.count = '8'
        rejected = False
        try:
            converted.count = 'invalid'
        except ValueError:
            rejected = True
        result['annotations_are_not_validators_and_declared_conversion_precedes_validation'] = (
            plain.count == '7' and converted.count == 8 and type(converted.count) is int and rejected)
    elif task == 'AT-U02':
        @attrs.define
        class Shared:
            """直接默认对象按引用共用。"""
            tags: list = attrs.field(default=[])

        @attrs.define
        class Owned:
            """工厂为每个实例创建容器。"""
            tags: list = attrs.field(factory=list)

        first, second, owned_first, owned_second = Shared(), Shared(), Owned(), Owned()
        first.tags.append('A')
        owned_first.tags.append('B')
        result['factory_separates_defaults_but_explicit_mutable_inputs_remain_shared'] = (
            second.tags == ['A'] and first.tags is second.tags and owned_second.tags == []
            and owned_first.tags is not owned_second.tags)
        supplied = []
        result['factory_separates_defaults_but_explicit_mutable_inputs_remain_shared'] &= (
            Owned(supplied).tags is supplied and Owned(supplied).tags is supplied)
    elif task == 'AT-C01':
        @attrs.frozen
        class Snapshot:
            """冻结字段绑定而非递归冻结容器。"""
            tags: list = attrs.field(factory=list)

        snapshot = Snapshot()
        snapshot.tags.append('LOCAL')
        rejected = False
        try:
            snapshot.tags = []
        except attrs.exceptions.FrozenInstanceError:
            rejected = True
        result['frozen_prevents_rebinding_but_does_not_deep_freeze_nested_values'] = snapshot.tags == ['LOCAL'] and rejected
    elif task == 'AT-C02':
        @attrs.define
        class Record:
            """演示初始化别名、共享容器及非初始化字段。"""
            _token: str = attrs.field(alias='token')
            tags: list = attrs.field(factory=list)
            cache: list = attrs.field(init=False, factory=list)

        original = Record('A', ['tag'])
        original.cache.append('OLD')
        changed = attrs.evolve(original, token='B')
        rejected = False
        try:
            attrs.evolve(original, _token='C')
        except TypeError:
            rejected = True
        result['evolve_calls_init_uses_aliases_and_is_not_a_deepcopy'] = (
            changed._token == 'B' and original._token == 'A' and changed.tags is original.tags
            and changed.cache == [] and changed.cache is not original.cache and rejected)
    elif task == 'AT-C03':
        @attrs.define
        class Credentials:
            """repr隐藏与显式导出政策分别声明。"""
            public: str
            secret: str = attrs.field(repr=False, metadata={'private': True})

        @attrs.define
        class Envelope:
            """嵌套输入用于核递归过滤。"""
            credentials: Credentials

        credentials = Credentials('VISIBLE', 'SYNTHETIC_SECRET')
        value = Envelope(credentials)
        raw = attrs.asdict(value)
        filtered = attrs.asdict(value, filter=lambda field, item: not field.metadata.get('private', False))
        result['repr_and_metadata_do_not_implicitly_redact_asdict_exports'] = (
            'SYNTHETIC_SECRET' not in repr(credentials)
            and raw['credentials']['secret'] == 'SYNTHETIC_SECRET'
            and filtered == {'credentials': {'public': 'VISIBLE'}}
            and attrs.asdict(value, recurse=False)['credentials'] is credentials)
    elif task == 'AT-P01':
        def ordered(instance, field, value):
            """验证完整区间关系。@param instance 对象。@param field 字段。@param value 新终点。@return None。"""
            if instance.start > value:
                raise ValueError('start exceeds end')

        @attrs.define
        class Window:
            """关系验证器只配置在end字段。"""
            start: int
            end: int = attrs.field(validator=ordered)

        live = Window(0, 10)
        live.start = 20
        intermediate_invalid = live.start > live.end
        live.end = 30
        control = Window(0, 10)
        rejected = False
        try:
            attrs.evolve(control, start=20)
        except ValueError:
            rejected = True
        result['field_hooks_are_not_a_multi_field_transaction_and_new_objects_can_gate_publication'] = (
            intermediate_invalid and (live.start, live.end) == (20, 30) and rejected
            and (control.start, control.end) == (0, 10))
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
