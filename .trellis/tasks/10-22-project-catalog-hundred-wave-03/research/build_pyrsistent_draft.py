"""制作持久状态快照、记录输入与批量验收任务。"""
from draft_content import build_project


def main() -> None:
    """按实际边界冻结五项任务，不填充无独立价值的诊断项。@return None。"""
    materials = {
        'materials/nested-state.md': 'values=["tea"];shallow=pmap({"items":values});deep=freeze({"items":values});values.append("book"). Compare identity and values of shallow["items"],deep["items"] and values. Explain outer persistence versus recursive conversion of supported built-in containers. This business probe exercises maps/records using the source Python vector fallback;the complete original regression separately builds and verifies pvectorc. Do not claim arbitrary custom objects become deeply immutable. No edits.\n',
        'materials/evolver.md': 'original=pmap({"tea":1});staging=original.evolver();staging["tea"]=2;first=staging.persistent();staging["tea"]=3;second=staging.persistent(). Explain original,first,second and staging after all calls. A draft editor must own the mutable evolver and explicitly publish snapshots. No edits or thread-safety guarantees.\n',
        'materials/field-conversion.md': 'Declare Item(PClass) with count=field(type=int,mandatory=True),and ConvertedItem(PClass) with count=field(type=int,mandatory=True,factory=int). Compare Item(count="3"),ConvertedItem(count="3"),and Item(count=3). Advise explicit input conversion and handling invalid conversion/type evidence. Type declaration alone must not be described as coercion. No edits.\n',
        'materials/extra-fields.md': 'Item has only count=field(type=int,mandatory=True). Input is {"count":3,"currency":"EUR"}. Compare Item.create(input) and Item.create(input,ignore_extra=True),including serialize() and the unchanged input. Advise a deliberate schema evolution policy for the currency field;do not claim ignored fields are retained or validated. No edits.\n',
        'materials/range-plan.md': 'Declare Range(PClass) with mandatory integer low/high and __invariant__ returning (self.low<=self.high,"low must not exceed high"). Starting from Range(low=0,high=5),compare .set(low=10),.set(low=10,high=20),and an evolver that sets low=10,attempts persistent(),then sets high=20 and publishes. Plan a UI applying a logically atomic range edit with complete validation and explicit publication. An evolver is a mutable staging object;this is not a database transaction or shared-memory concurrency contract. No implementation.\n'}
    definitions = [
        ('PS-U01', 'understand', '界定嵌套状态的不可变范围', 'Explain the exact map/freeze/mutation controls. No edits.', ['materials/nested-state.md'], 'explained',
            'pmap preserves the original mutable list object,so shallow items becomes tea,book. freeze before mutation recursively converts that built-in list and deep items stays tea. Outer persistent containers do not by themselves freeze values;freeze only handles supported types and is not a universal deep-copy or immutable-custom-object guarantee.', ['persistent_outer_map_does_not_freeze_mutable_values']),
        ('PS-U02', 'understand', '追踪编辑草稿和已发布快照', 'Explain all evolver and snapshot states after the complete sequence. No edits.', ['materials/evolver.md'], 'explained',
            'Original remains tea1,first remains tea2,second is tea3 and staging currently reads3. The mutable evolver can continue after publication while earlier persistent snapshots retain their contents. Own the staging lifetime and capture the returned snapshot;no concurrency or arbitrary-value immutability guarantee follows.', ['evolver_is_mutable_and_published_snapshots_are_independent']),
        ('PS-C01', 'consult', '选择记录字段的显式转换边界', 'Advise type checking versus the actual factory controls. No edits.', ['materials/field-conversion.md'], 'advice_no_code_change',
            'Item(count=string3) raises PTypeError;the explicit int factory converts the supplied string to integer3 before checking. Item(count=integer3) succeeds directly. Choose conversion policy separately,handle factory errors and domain constraints,and do not infer coercion from type=int alone.', ['field_type_checks_do_not_imply_conversion']),
        ('PS-C02', 'consult', '决定未知字段的兼容策略', 'Advise the exact strict/ignore-extra behavior and loss of unmodeled currency. No implementation.', ['materials/extra-fields.md'], 'advice_no_code_change',
            'The strict create control raises AttributeError for currency. ignore_extra=True creates a record serializing only count3;it leaves the input dictionary unchanged but drops currency from the record rather than preserving or validating it. Select reject,explicitly model,or deliberately ignore based on the schema contract and test round trips.', ['ignoring_extra_fields_is_explicit_and_drops_unmodeled_input']),
        ('PS-P01', 'plan', '规划区间字段的整体提交与验收', 'Plan complete range-edit validation and publication from all supplied controls. No implementation.', ['materials/range-plan.md'], 'planned_without_library_change',
            'Setting low10 alone against high5 fails the cross-field invariant. Updating low10/high20 together succeeds. The evolver holds low10 temporarily,but persistent() fails until high20 is set;then it publishes the same valid range,while original stays0..5. Collect a complete logical edit,validate/publish a persistent value,retain prior state on validation failure and define application error handling. Do not claim the mutable staging object supplies a database transaction or thread-safety.', ['cross_field_invariants_validate_complete_published_records'])]
    scenes = [('PS-S01', '状态和快照边界', '分清嵌套值和可变草稿', ['PS-U01', 'PS-U02']),
        ('PS-S02', '输入记录合同', '显式转换并决定未知字段', ['PS-C01', 'PS-C02']),
        ('PS-S03', '整体更新验收', '只发布完整有效区间', ['PS-P01'])]
    build_project('pyrsistent', {'title': 'Pyrsistent状态快照工作场景', 'category': '不可变状态与记录验收',
        'description': '嵌套不可变范围、可变草稿与持久快照、字段转换、未知字段和跨字段验收。'}, definitions, scenes, materials)


if __name__ == '__main__':
    main()
