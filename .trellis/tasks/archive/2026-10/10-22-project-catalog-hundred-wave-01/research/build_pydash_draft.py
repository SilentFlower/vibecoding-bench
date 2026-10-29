"""制作Pydash查询、更新所有权、合并取证和公开投影任务。"""
from draft_content import build_project


def main() -> None:
    """保存四场景八个独立只读任务，无隐式答案依赖。@return None。"""
    materials = {
        'materials/lookups.md': 'Complete object {nil:None,disabled:False,count:0}. Compare get for each existing field and a missing field with one explicit unique sentinel, plus has for nil/missing. Separately query {"a.b":{"value":1},"a":{"b":{"value":2}}} with string a.b.value and token list ["a.b","value"]. An external field may contain literal dots. No files may be changed.\n',
        'materials/updates.md': 'On fresh empty dicts compare set_(obj,"orders[0].id","A") with set_(obj,"orders.0.id","A"), including returned identity and exact shape. Separately deep-clone {orders:[{id:A}]} and set the cloned first id toB. A patch-preview service must isolate its baseline and accept only declared field/index paths, rejecting undeclared or resource-unbounded user paths rather than executing them. No implementation or project edits are requested.\n',
        'materials/merge.md': 'Destination={nested:{keep:1},values:[1,2]}; source={nested:{added:2},values:[9],fresh:{x:1}}. Run merge and inspect returned identity, destination, source and whether editing the new result.fresh changes source.fresh. Separately merge tags[a] with tags[b] using an explicit list-concatenating iteratee; compare an iteratee returning None with one returning0 for limit5/source7. No project files may be changed.\n',
        'materials/alias-symptom.md': 'Two previews intended to use the same baseline appear to affect each other. The complete object construction, merge calls, identities and time order have not been supplied. Investigate before assigning a cause.\n',
        'disclosure/alias.md': 'Complete synthetic sequence: baseline={"limits":{"daily":1}}; a=merge(baseline,{"limits":{"daily":2}}); b=merge(baseline,{"name":"B"}). No clone is made. Inspect a is b is baseline, final limits and whether a also has nameB. No database or external service exists.\n',
        'disclosure/unavailable.md': 'Object construction, call sequence and identity evidence cannot be supplied. No additional reproduction is available.\n',
        'materials/profile.md': 'Synthetic profile={name:Ada,password:synthetic-password,contact:{email:a@example.test,token:synthetic-private-token}}. Compare pick(name,contact), pick(name,contact.email), and omit(password,contact.token), then inspect source ownership. A public response may expose only name and contact.email; do not silently return an entire nested mapping or claim an arbitrary unknown schema has been sanitized. No files may be changed.\n'}
    definitions = [
        ('PD-U01', 'understand', '区分缺失字段和已存在的空值零值',
            'Trace the complete sentinel/has lookup controls and give exact identity/existence results. Explain why falsey fallback syntax would answer a different business question. Do not edit files.',
            ['materials/lookups.md'], 'explained',
            'Existing None,False,0 are returned as actual values; only a missing path returns the explicit sentinel. has(nil) isTrue and has(missing) isFalse. A truthiness-based fallback conflates these states and is not the same as a missing-value contract.', ['explicit_missing_sentinel_distinguishes_present_falsey_values']),
        ('PD-C01', 'consult', '为含点的外部字段选择明确路径表示',
            'Recommend an existing path representation for the complete literal-dot field example. Compare both actual results and preserve the external schema without implementation.',
            ['materials/lookups.md'], 'advice_no_code_change',
            'String a.b.value traverses nested a/b/value and returns2. Token list[a.b,value] preserves the first literal key and returns1. Own the field/path protocol explicitly rather than silently splitting an externally supplied literal key or claiming a new path parser is needed.', ['path_list_preserves_a_literal_dot_key']),
        ('PD-U02', 'understand', '解释路径更新的原地副作用和列表创建',
            'Trace the complete two set_ controls, exact shapes and returned identities. Explain bracket-index versus dotted-numeric syntax using the pinned implementation. Do not change project files.',
            ['materials/updates.md'], 'explained',
            'set_ modifies and returns the original dict. orders[0].id creates a list of one object; orders.0.id creates an orders mapping with string key0. Path spelling determines missing-container shape, not merely equivalent display syntax.', ['set_is_in_place_and_index_syntax_controls_created_shape']),
        ('PD-P01', 'plan', '规划隔离基线的声明式补丁预览',
            'Plan the complete preview isolation/path-acceptance requirement with current APIs. Identify baseline ownership, a normal copied update and rejection/resource controls. Do not execute untrusted paths or implement a service.',
            ['materials/updates.md'], 'planned_without_library_change',
            'Deep-clone the declared plain-data baseline before set_ updates and keep candidate/source ownership explicit; the supplied clone becomes idB while original remainsA. Validate an allowlisted typed path/index protocol and bounded sizes before applying updates, then validate resulting business schema and return a preview. set_ alone is mutation, not authorization, schema validation or a transaction.', ['deep_clone_can_isolate_a_declared_update']),
        ('PD-U03', 'understand', '追踪合并目标、源复制和列表索引',
            'Trace the complete merge reproduction including returned identity, list contents and source after the later result edit. Do not transfer assumptions from other merge libraries or modify files.',
            ['materials/merge.md'], 'explained',
            'merge returns/mutates the destination, retaining nested.keep and adding nested.added. Lists merge by index, yielding[9,2], not concatenation. Source values are deep-copied for merging, so editing result.fresh does not change source.fresh. Destination mutation and source copying are distinct ownership guarantees.', ['merge_mutates_destination_and_merges_lists_by_index']),
        ('PD-C02', 'consult', '为标签合并选择已有回调语义',
            'Meet the complete list-concatenation requirement with current merge_with. Explain actual callback arguments, None delegation and the explicit zero control without implementation.',
            ['materials/merge.md'], 'advice_no_code_change',
            'Use iteratee with the real left/right/key/destination/source arguments, returning concatenation only when both values are lists and None to delegate other cases. tags becomes[a,b]. Returning None for limit delegates to7; returning0 explicitly produces0. None is not a universal clear-to-null override sentinel, and falsy results other thanNone remain meaningful.', ['custom_merge_uses_none_as_delegate_and_keeps_falsey_results']),
        ('PD-D01', 'diagnose', '先取对象身份和调用时序再定位预览串扰',
            'Investigate the supplied preview-interference symptom. Request actual construction, merge calls, object identities and order before choosing a cause. Diagnose disclosed evidence only, or close with an evidence plan when unavailable. Do not modify files.',
            ['materials/alias-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual construction/call/identity evidence and intended baseline ownership. Explain only disclosed behavior, without assuming aliasing, global state or a library bug from the symptom alone. insufficient_information is valid when the reproduction is unavailable.', None),
        ('PD-C03', 'consult', '把公开字段白名单落实到嵌套边界',
            'Meet the complete public-profile output requirement using current projection APIs. Compare exact whole-contact/deep-path/omit controls and source ownership; do not claim a generic sanitizer or edit files.',
            ['materials/profile.md'], 'advice_no_code_change',
            'Picking whole contact also retains its synthetic token and shares that nested mapping, so top-level selection misses the requirement. Picking name and contact.email yields only those declared fields. Deep-path omit(password,contact.token) is already supported and deep-clones for the nested removal, preserving the original, but an omission policy must still consider future unknown fields. Prefer an explicit nested whitelist for this declared output.', ['nested_projection_boundary_must_be_explicit'])]
    scenes = [('PD-S01', '外部字段与缺失协议', '区分存在性、假值和字面路径', ['PD-U01', 'PD-C01']),
        ('PD-S02', '补丁预览与对象所有权', '明确路径结构、原地更新和基线隔离', ['PD-U02', 'PD-P01']),
        ('PD-S03', '合并政策与串扰取证', '核目标副作用、源复制和列表自定义', ['PD-U03', 'PD-C02', 'PD-D01']),
        ('PD-S04', '公开资料投影', '按明确嵌套白名单生成公开结果', ['PD-C03'])]
    build_project('pydash', {'title': 'Pydash数据对象工作场景', 'category': '深路径与对象变换',
        'description': '固定真实源码上的缺失协议、字面键、预览隔离、合并取证和嵌套公开字段八项独立只读任务。'}, definitions, scenes, materials,
        branches={'PD-D01': [{'id': 'identity-evidence', 'when': 'The actual construction, calls, object identities and order have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/alias.md']}]},
        extra_entries={'PD-S03': [{'id': 'diagnose_only', 'task_ids': ['PD-D01']},
            {'id': 'unavailable', 'task_ids': ['PD-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
