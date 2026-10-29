"""制作输入来源、验证链与对象更新的实际表单任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项独立只读任务。@return None。"""
    materials = {
        'materials/required-zero.md': 'Compare two Forms with count=IntegerField(validators=[DataRequired()]) versus [InputRequired()],using actual multi-value submitted input count=["0"]. Also construct the InputRequired form with data={"count":3} and no formdata. Explain converted values,raw submission and validation. No edits.\n',
        'materials/checkbox.md': 'CheckboxForm has enabled=BooleanField(). The original synthetic object has enabled=True. Compare CheckboxForm(obj=obj) with CheckboxForm(formdata=empty_multi_value_input,obj=obj),including raw_data and data. Explain initial display versus an unchecked submission. No edits.\n',
        'materials/input-adapter.md': 'QuantityForm has count=IntegerField(). Compare formdata={"count":"3"} with an explicitly defined multi-value wrapper whose getlist("count") returns ["3"]. Explain exact input-protocol rejection,accepted raw_data/data,and how formdata differs from data prefill before planning a JSON adapter. No implementation.\n',
        'materials/optional-source.md': 'OptionalQuantity has count=IntegerField(validators=[Optional(),NumberRange(min=0)]). Compare construction with data={"count":-1} and no formdata,against submitted multi-value count=["-1"]. Inspect raw_data,data and validate(). Advise explicit object/domain validation ownership;do not describe the existing Optional raw-input contract as an all-source range check. No edits.\n',
        'materials/populate-plan.md': 'OutputForm declares first then second StringField. Both have valid strings new/changed and form.validate() succeeds. A synthetic target has first="old" and second property returning original whose setter raises ValueError("synthetic setter rejected"). Calling populate_obj updates first,then fails on second. Plan complete application validation,staging and publication/failure policy from this actual partial write. No real object/database writes or implementation are authorized.\n',
        'disclosure/shared-rules.md': 'Complete reproduction: SharedForm.name=StringField();filter_name appends filter to a local calls list and returns value+"!";validate_name appends validate. Reuse filters={name:[]} across two constructions with data name=x,then reuse validators={name:[]} across two validate calls on the first form. Actual filter and validator inner-list lengths both become2,values are x! and x!!,and calls are filter,filter,filter,validate,validate,validate. BaseForm.process copies only the outer dict before appending a bound inline filter;Form.validate copies only the outer dict before appending its inline validator. No other components modify these lists.\n',
        'disclosure/unavailable.md': 'The complete form declarations,inline hooks,caller-owned extra-rule lists,reuse order and observed calls cannot be supplied.\n'}
    definitions = [
        ('WF-U01', 'understand', '区分库存零值和必填输入', 'Explain every supplied converted-data/raw-input control. No edits.', ['materials/required-zero.md'], 'explained',
            'Both submitted zeros convert to integer0. DataRequired rejects falsey converted0;InputRequired accepts nonempty raw string0. An InputRequired form prefilled with3 but no actual formdata fails because initial data is not submitted input. Select the validator for the business contract.', ['required_input_and_truthy_converted_data_are_distinct']),
        ('WF-U02', 'understand', '区分初始勾选状态与空提交', 'Explain both complete checkbox input-source controls. No edits.', ['materials/checkbox.md'], 'explained',
            'Without formdata the original True is retained and raw_data isNone. With the empty submitted wrapper raw_data is[] and BooleanField sets dataFalse. The empty submission represents an unchecked input rather than a request to keep the initial object state.', ['missing_checkbox_submission_is_not_the_initial_object_value']),
        ('WF-C01', 'consult', '明确表单提交适配协议', 'Advise the actual multidict protocol and prefill distinction. No implementation.', ['materials/input-adapter.md'], 'advice_no_code_change',
            'The plain dict formdata raises TypeError requiring a multidict wrapper with getlist. The explicit list-valued protocol returns raw[3 as string] and converted integer3. Preserve repeated-value semantics when adapting submitted input and distinguish that adaptation from data= object prefill;no new built-in JSON adapter is implied.', ['submitted_input_requires_a_multivalue_getlist_protocol']),
        ('WF-C02', 'consult', '选择可选字段的来源验证策略', 'Advise actual Optional behavior from both complete controls. No edits.', ['materials/optional-source.md'], 'advice_no_code_change',
            'Both values are integer-1,but initial raw_dataNone makes Optional stop validation so the prefilled form succeeds;submitted raw[-1 as string] proceeds to NumberRange and fails. Use separate explicit domain/object validation or deliberately chosen source policy when all values must be checked. Preserve the current Optional input contract rather than assume it validates every data source.', ['optional_checks_raw_submission_instead_of_validating_all_initial_values']),
        ('WF-P01', 'plan', '规划对象填充的失败边界', 'Plan validation/staging/publication from the complete partial-write control. No implementation.', ['materials/populate-plan.md'], 'planned_without_library_change',
            'Form validation succeeds but populate_obj writes fields sequentially;the second setter raises after first becomes new,while second stays original. Validate business state and target operations,stage an independent result where appropriate,and define explicit publication/recovery and error handling. Form validation is not a guarantee that object setters succeed or that populate_obj rolls back atomically.', ['validation_does_not_make_sequential_object_population_atomic']),
        ('WF-D01', 'diagnose', '诊断额外规则被重复执行', 'Extra field rules unexpectedly run more often after reuse. Request complete field/hooks,caller lists,reuse order and call observations before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually consumed declarations,rule ownership/reuse and call observations. Ask for missing complete controls;when established,trace actual list construction and mutation and propose an explicit per-call ownership workaround. Missing evidence supports insufficient_information. Do not invent a cause or turn diagnosis into an unrequested library patch.', None)]
    scenes = [('WF-S01', '提交与初始值', '区分零值和缺少勾选', ['WF-U01', 'WF-U02']),
        ('WF-S02', '输入适配与规则来源', '明确协议和校验边界', ['WF-C01', 'WF-C02']),
        ('WF-S03', '对象填充方案', '明确暂存与失败策略', ['WF-P01']),
        ('WF-S04', '额外规则诊断', '取得列表复用证据', ['WF-D01'])]
    build_project('wtforms', {'title': 'WTForms商品表单工作场景', 'category': '输入、验证与对象边界',
        'description': '库存零值、勾选提交、多值适配、可选规则、对象填充和规则复用诊断。'}, definitions, scenes, materials,
        branches={'WF-D01': [{'id': 'complete-shared-rules',
            'when': 'Complete field/hooks,caller-owned rule lists,reuse order and call observations have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/shared-rules.md']}]},
        extra_entries={'WF-S04': [{'id': 'unavailable', 'task_ids': ['WF-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
