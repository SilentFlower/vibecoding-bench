"""制作Box键准入、读取副作用、覆盖取证、点路径与配置转换任务。"""
from draft_content import build_project


def main() -> None:
    """保存五场景八个独立只读任务，保留实际问题与已有能力边界。@return None。"""
    materials = {
        'materials/attribute-keys.md': 'Construct Box({"items":["A"],"first name":"Ada"}). Compare attribute items with ["items"], attribute first_name with the original key and inspect actual keys. Separately ingest keys a-b and a b with values1 and2: compare default conversion, box_duplicates=error, and conversion_box=False for an attribute-facing application that cannot silently select an ambiguous alias. No project edits are authorized.\n',
        'materials/missing.md': 'Compare Box(default_box=True).customer.region with a retained initially empty object. Separately compare explicit get("customer",None), default_box_create_on_get=False and an ordinary Box missing attribute. A configuration preflight must detect an absent required customer/region without silently creating structure or treating an empty fallback object as a valid value. No files may be changed.\n',
        'materials/overlay-symptom.md': 'After applying an environment override, a database connection setting disappeared. The complete base/override objects, exact update method, flags and observed before/after values are not supplied. Investigate before deciding why.\n',
        'disclosure/overlay.md': 'Complete synthetic reproduction: base=Box({"db":{"host":"A","port":5432},"tags":["base"]}); base.update({"db":{"host":"B"}}). The db object afterward contains hostB without port. No merge_update call or other mutation is present.\n',
        'disclosure/unavailable.md': 'The complete objects, update method/options and before/after values cannot be supplied. No additional reproduction exists.\n',
        'materials/merge-policy.md': 'Fresh base={"db":{"host":"A","port":5432},"tags":["base"]}; override={"db":{"host":"B"},"tags":["new","new"]}. The business requires retaining untouched nested database fields. Compare update with existing merge_update and its default/box_merge_lists=extend/unique list policies. Duplicate tags must follow an explicit selected policy; do not change either source dictionary or implement a new merge engine.\n',
        'materials/dots.md': 'Pass the complete insertion-ordered input {"db.host":"flat","db":{"host":"nested"}} into fresh Boxes with box_dots=True and default_box left False, then with default_box=True. Also compare default dots disabled and dots enabled plus box_dots_exclude matching exactly db.host. Record construction errors or actual dictionaries and ["db.host"]/["db"]["host"] as applicable. Separately reverse the two input-key insertion positions with dots enabled/default_box=False, and test a nested-only Box with dots enabled/disabled. An external schema permits literal dots in keys; determine what construction itself requires and changes. No edits are authorized.\n',
        'materials/config-casts.md': 'ConfigBox values: disabled="false", spaced=" FALSE ", unknown="maybe", count="5", bad="five". Compare .bool and .int results with the retained original values. A business switch must accept a defined strict vocabulary and reject unknown input rather than approximating every truthy string. Recommend explicit normalization/validation ownership with existing capabilities; no file changes are authorized.\n'}
    definitions = [
        ('BX-U01', 'understand', '区分字典方法、属性别名和原始键',
            'Trace the complete first Box example and give actual attribute/item/key behavior. Explain why method names and converted aliases do not replace exact-key access. Do not modify files.',
            ['materials/attribute-keys.md'], 'explained',
            'items remains the dictionary method, while ["items"] returns the payload list. first_name accesses original first name through a converted alias, and original keys remain items/first name. Attribute convenience is not a guarantee that arbitrary external keys are safe or renamed uniquely.', ['attributes_keep_original_keys_and_dictionary_methods']),
        ('BX-C01', 'consult', '拒绝有歧义的属性别名配置',
            'Meet the complete attribute-facing ingestion requirement for the supplied two distinct keys. Compare actual default/error/no-conversion controls and recommend an explicit accepted-key policy without implementation.',
            ['materials/attribute-keys.md'], 'advice_no_code_change',
            'Default conversion preserves both exact keys but a_b resolves to the later value2. box_duplicates=error rejects the conversion collision. An exact-key interface can disable conversion_box and retain both keys, but must not promise an unambiguous attribute alias. Choose rejection/explicit key ownership rather than silently discarding original data.', ['conversion_collisions_can_be_rejected_or_bypassed_explicitly']),
        ('BX-U02', 'understand', '追踪默认读取为何创建嵌套配置',
            'Trace the retained default_box=True read experiment and report the final object. Explain whether this lookup is free of in-memory mutation and distinguish that from permission to edit project files.',
            ['materials/missing.md'], 'explained',
            'Accessing customer.region creates nested default Boxes, leaving {customer:{region:{}}}. The original object changes through lookup under these options. It is not evidence that those required business values were supplied or a filesystem modification.', ['default_reads_can_create_nested_configuration']),
        ('BX-P01', 'plan', '规划不自动补结构的必填配置预检',
            'Plan the supplied required-customer/region preflight using current APIs and explicit schema rules. Compare noncreating controls and actual missing behavior; do not invent a library validator or implement changes.',
            ['materials/missing.md'], 'planned_without_library_change',
            'Use explicit get with a missing sentinel/default or ordinary Box missing-key behavior, and avoid auto-creating reads during presence checks. default_box_create_on_get=False returns detached fallbacks without populating the original but still does not validate required values. Define presence, type and allowed-empty business rules separately; do not accept an empty fallback as supplied configuration.', ['explicit_get_and_noncreating_default_do_not_validate_required_fields']),
        ('BX-D01', 'diagnose', '先取实际覆盖调用再定位消失的连接设置',
            'Investigate the supplied disappeared-setting symptom. Request complete base/override objects, exact method/options and before/after values before assigning a cause. Diagnose disclosed evidence only or close with an evidence plan if unavailable. Do not change files.',
            ['materials/overlay-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient objects and update/merge method/options with observed output. Explain only what disclosed evidence supports; missing data alone cannot establish shallow replacement, default creation or a defect. insufficient_information is valid when reproduction cannot be supplied.', None),
        ('BX-C02', 'consult', '用已有递归合并并明确列表重复政策',
            'Meet the complete nested-field/list-policy requirement using existing methods. Give actual update versus merge_update and default/extend/unique results on fresh objects; do not change source mappings or build a new merge feature.',
            ['materials/merge-policy.md'], 'advice_no_code_change',
            'update replaces db with hostB and loses port. merge_update retains port5432 and changes hostB. Default tags replace with[new,new], extend gives[base,new,new], unique gives[base,new]. These methods mutate the destination, so use an explicitly owned destination/fresh Box and preserve source mappings. Select the required list policy rather than assume all recursive merge is concatenation or pure.', ['existing_recursive_merge_and_list_policy_are_distinct']),
        ('BX-U03', 'understand', '区分构造时路径展开和字面点键',
            'Trace the complete ordered-input and dotted-option controls, including actual resulting dictionaries and lookups. Explain construction-time expansion, reversed input order and existing literal-key controls. Do not change files.',
            ['materials/dots.md'], 'explained',
            'Construction uses path-aware __setitem__. With dots enabled/default_box=False, the first db.host item raises BoxKeyError because db does not yet exist. With default_box=True it creates that path, then the later db mapping replaces it, yielding only nested host=nested. Reversing input positions makes the parent exist and yields host=flat. Dots disabled or an explicit exclusion preserves literal db.host=flat alongside nested host=nested. A nested-only dotted lookup resolves only when enabled. Do not claim constructing arbitrary dotted input always succeeds or preserves literal keys.', ['dotted_input_keys_require_explicit_construction_policy']),
        ('BX-C03', 'consult', '为严格业务开关补明确词汇校验',
            'Explain the complete ConfigBox casting results and recommend a strict business-input policy using existing behavior. Include whitespace, unknown values, integer failure and original data ownership. Do not alter global casting or implement changes.',
            ['materials/config-casts.md'], 'advice_with_limits',
            'bool(false) isFalse, but spaced FALSE and unknown maybe areTrue under approximate casting; int5 is5 and intfive raisesValueError. Conversions return values without replacing original string count. Normalize whitespace/case deliberately, validate an explicit accepted vocabulary/type and reject unknown values before using the business switch. Do not claim ConfigBox.bool is already a strict schema or silently change its global semantics.', ['config_casting_is_approximate_not_a_strict_schema'])]
    scenes = [('BX-S01', '外部键与属性准入', '保留原键并拒绝模糊属性入口', ['BX-U01', 'BX-C01']),
        ('BX-S02', '默认读取与必填预检', '分清自动创建、缺失证据和业务校验', ['BX-U02', 'BX-P01']),
        ('BX-S03', '环境覆盖与合并政策', '从真实调用取证并选择已有嵌套／列表规则', ['BX-D01', 'BX-C02']),
        ('BX-S04', '字面点键协议', '核构造时路径展开及明确的字面键政策', ['BX-U03']),
        ('BX-S05', '配置值严格转换', '把近似转换与业务词汇校验分开', ['BX-C03'])]
    build_project('python-box', {'title': 'Python-Box配置访问工作场景', 'category': '配置对象与字段治理',
        'description': '固定真实纯Python源码上的属性键、默认读取、覆盖取证、已有递归合并、点键与严格转换八项独立只读任务。'}, definitions, scenes, materials,
        branches={'BX-D01': [{'id': 'overlay-evidence', 'when': 'The actual objects, update method/options and before/after values have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/overlay.md']}]},
        extra_entries={'BX-S03': [{'id': 'diagnose_only', 'task_ids': ['BX-D01']},
            {'id': 'unavailable', 'task_ids': ['BX-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
