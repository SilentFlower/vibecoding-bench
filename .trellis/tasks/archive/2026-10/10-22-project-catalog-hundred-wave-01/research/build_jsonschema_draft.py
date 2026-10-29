"""制作JSON配置、格式取证、数值适配、组合闭合及离线引用任务。"""
from draft_content import build_project


def main() -> None:
    """保存五场景九项独立只读任务，不把已有扩展API虚构为缺失能力。@return None。"""
    materials = {
        'materials/config.md': 'Schema: {"type":"object","properties":{"retries":{"type":"integer","default":3}},"required":["retries"]}. Validate an initially empty dict and compare with {"retries":3}; inspect whether validation inserts defaults or changes its input. No mutation is authorized.\n',
        'materials/errors.json': '{"schema":{"type":"object","properties":{"orders":{"type":"array","items":{"type":"object","properties":{"qty":{"type":"integer","minimum":1}},"required":["qty"]}}}},"payload":{"orders":[{"qty":0},{"qty":"many"},{}]}}\n',
        'materials/error-report.md': 'An import preview must show every independent invalid order with structured instance path, keyword and a useful message, without echoing the entire private input. Compare reusable checked-schema validators and iter_errors with the single exception from validate. No code change is requested.\n',
        'materials/format-symptom.md': 'A value that the importer team considers an invalid email was accepted. The actual schema, validator construction, checker settings and sample have not been supplied. Investigate before assigning a cause.\n',
        'disclosure/format.md': 'Complete synthetic call: Draft202012Validator({"type":"string","format":"email"}).is_valid("broken") returns True. No format_checker was passed. Compare the same schema with an explicit FormatChecker and valid a@example.test. No actual account or email service exists.\n',
        'disclosure/unavailable.md': 'The schema, construction call, format checker and original value cannot be provided. No further reproduction is available.\n',
        'materials/bin-format.md': 'Only this warehouse validator should enforce format warehouse-bin: strings must be BIN- followed by decimal digits. The format check function raises ValueError for invalid strings and leaves nonstrings to the schema type keyword. Compare BIN-12 with rack-A, inspect ValidationError.cause, and leave unrelated FormatChecker instances unchanged. A typo in a format name must be considered explicitly. Do not edit files.\n',
        'materials/types.md': 'Compare integer validation for True,1,1.0,1.5 and Decimal("2"). A separate in-process accounting adapter wants finite integral Decimal values accepted but fractional/NaN values and booleans rejected. Ordinary JSON wire payloads and standard Draft202012Validator behavior must keep their existing meaning. Plan with existing TypeChecker.redefine and validators.extend; no implementation is authorized.\n',
        'materials/composition.json': '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","allOf":[{"properties":{"name":{"type":"string"}},"required":["name"]},{"properties":{"age":{"type":"integer"}},"required":["age"]}]}\n',
        'materials/composition.md': 'Validate {"name":"Ada","age":30}. First close each allOf branch independently with additionalProperties:false. Separately close the original combined schema using root unevaluatedProperties:false; also test an extra debug:true property. Compare explicit Draft202012Validator and Draft7Validator. The business wants the two declared fields accepted and all other fields rejected. No schema edits are requested.\n',
        'materials/references.md': 'A fully offline importer has one approved resource: {"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:catalog:quantity","type":"integer","minimum":1}. Use an explicit referencing.Registry with this resource and a root $ref to it. Compare 2 and 0 and unknown urn:catalog:missing. Plan an allowlisted in-memory resource/version catalog with deterministic missing-reference failure; no URL fetching, filesystem discovery or production deployment is authorized.\n'}
    definitions = [
        ('JV-U01', 'understand', '区分配置默认值注解和实际填充值',
            'Trace the complete required/default configuration example. Give validation results, errors and final input state; distinguish validation from any proposed normalization. Do not change files or fill defaults.',
            ['materials/config.md'], 'explained',
            'The empty dict remains empty and fails required; default3 is an annotation, not mutation. Explicit retries3 succeeds. A normalization/default-application policy would be separate application behavior and needs explicit ownership.', ['default_is_annotation_and_input_stays_unchanged']),
        ('JV-C01', 'consult', '为导入预览选择完整结构化错误清单',
            'Recommend current validation APIs for the supplied full import-preview error-report requirement. Identify all three actual instance locations and keywords, reusable schema validation and output privacy limits. Do not implement.',
            ['materials/errors.json', 'materials/error-report.md'], 'advice_no_code_change',
            'iter_errors yields minimum at orders/0/qty, type at orders/1/qty and required at orders/2; validate raises one selected best-match error, not a complete report. Check the schema once then reuse its validator. Sort paths deliberately for presentation, preserve structured paths/keyword and avoid dumping full input or parsing the exception string.', ['error_list_keeps_paths_and_independent_failures']),
        ('JV-D01', 'diagnose', '先取校验调用再判断邮箱为何通过',
            'Investigate the supplied accepted-email symptom. Request the actual schema, sample and validator/checker construction before deciding the cause. Relate only disclosed evidence to the pinned API; if unavailable, close with a bounded evidence plan. Do not modify files.',
            ['materials/format-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual schema/value and constructor/checker evidence; acceptance alone does not prove a library bug. Explain only the disclosed call and a compatible current-API remedy, or use insufficient_information when the call cannot be supplied. Do not assume a missing checker or claim an observed format failure before disclosure.', None),
        ('JV-C02', 'consult', '限定货位格式检查器的作用域和错误原因',
            'Meet the supplied warehouse-bin validation requirement using existing APIs without implementation. Explain checker activation, local registration, ValueError handling/cause, valid/invalid controls and unknown-format handling.',
            ['materials/bin-format.md'], 'advice_no_code_change',
            'Create a specific FormatChecker, register via its checks(format,raises=ValueError), and pass it to the validator. BIN-12 succeeds and rack-A produces a format error with ValueError cause. New unrelated checkers remain unchanged. Unknown/typo format names are ignored, so required-format names need application schema/catalog validation rather than presumed rejection.', ['format_needs_explicit_checker_and_unknown_is_ignored', 'local_format_does_not_mutate_other_checkers']),
        ('JV-U02', 'understand', '区分JSON整数和Python布尔继承关系',
            'Trace the supplied integer type examples under the fixed 2020-12 validator, including the in-process Decimal control. Explain why Python isinstance assumptions alone are insufficient. Do not change files.',
            ['materials/types.md'], 'explained',
            'True fails integer despite bool inheriting int;1 and1.0 pass,1.5 fails, and Decimal2 is not an ordinary integer in this type checker. These are validation semantics, not automatic conversion or wire serialization.', ['integer_excludes_bool_but_accepts_integral_float']),
        ('JV-P01', 'plan', '规划局部Decimal整数适配而不改变全局类型',
            'Plan the supplied in-process accounting compatibility requirement with existing extension APIs. Preserve bool rejection and standard validator behavior; distinguish this adapter from JSON wire encoding. No implementation is authorized.',
            ['materials/types.md'], 'planned_without_library_change',
            'Use the original checker plus a finite/integral Decimal predicate in a newly returned TypeChecker, then validators.extend into a locally owned class. Do not recurse by calling the redefined checker on the same type, mutate global TYPE_CHECKER or silently rewrite META_SCHEMA. Test2/2.5/NaN/bool and unchanged standard behavior; define serialization separately.', ['decimal_extension_is_local_and_keeps_integer_rules']),
        ('JV-U03', 'understand', '解释组合schema分支为何互相拒绝字段',
            'Trace the supplied payload after closing each allOf branch independently. Explain exactly which scope additionalProperties examines and why this is not cross-branch property union. Do not edit the schema.',
            ['materials/composition.json', 'materials/composition.md'], 'explained',
            'Each branch sees the other field as additional: the name branch rejects age and the age branch rejects name. allOf is intersection of validations, not a schema merger or automatic union of properties.', ['additional_properties_is_branch_local']),
        ('JV-C03', 'consult', '为组合对象选择有明确draft的闭合策略',
            'Recommend an existing schema/validator strategy meeting the complete two-fields-only requirement. Compare actual 2020-12 and draft7 behavior, valid and extra-property controls; no implementation is requested.',
            ['materials/composition.json', 'materials/composition.md'], 'advice_no_code_change',
            'For the original successful allOf schemas, root unevaluatedProperties:false with 2020-12 accepts name/age and rejects debug. Draft7 ignores this unsupported keyword, so pin/select the actual dialect rather than assuming an explicit Draft7Validator honors the schema URI. Repeating root properties is another scoped compatibility option; do not promise a generic schema merge.', ['unevaluated_properties_closes_successfully_evaluated_composition']),
        ('JV-P02', 'plan', '规划离线schema引用目录与缺失资源失败',
            'Plan the complete approved-resource offline importer using the installed referencing APIs and fixed validator. Explain registration ownership,2/0 controls, missing-resource behavior and version/dialect policy. Do not fetch external resources or implement/deploy anything.',
            ['materials/references.md'], 'planned_without_library_change',
            'Create Resource.from_contents with its declared dialect and use the returned Registry.with_resource result; registries are immutable. Pass that explicit registry into Draft202012Validator:2 passes,0 fails minimum,unknown URN raises referencing.exceptions.Unresolvable. Validate versioned allowlisted resource completeness and fail closed on missing entries, with no implicit remote/file retrieval or changes to global defaults.', ['registry_has_explicit_resources_and_rejects_unknown'])]
    scenes = [('JV-S01', '配置导入与错误预览', '明确注解、副作用和完整错误输出', ['JV-U01', 'JV-C01']),
        ('JV-S02', '邮箱取证与货位格式', '区分实际调用、检查器启用和局部格式注册', ['JV-D01', 'JV-C02']),
        ('JV-S03', '进程内数值兼容', '保留标准JSON语义并隔离Decimal扩展', ['JV-U02', 'JV-P01']),
        ('JV-S04', '组合schema字段闭合', '按真实draft选择分支约束与求值后闭合', ['JV-U03', 'JV-C03']),
        ('JV-S05', '离线schema引用目录', '用明确资源集合保证离线引用结果可解释', ['JV-P02'])]
    build_project('jsonschema', {'title': 'JSON Schema数据准入工作场景', 'category': '结构校验与schema治理',
        'description': '固定真实源码上的配置注解、完整错误、格式取证、数值兼容、组合闭合和离线引用九项独立只读任务。'},
        definitions, scenes, materials,
        branches={'JV-D01': [{'id': 'format-call', 'when': 'The actual schema, sample and validator/checker construction are not yet supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/format.md']}]},
        extra_entries={'JV-S02': [{'id': 'diagnose_only', 'task_ids': ['JV-D01']},
            {'id': 'unavailable', 'task_ids': ['JV-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
