"""观察表单输入来源、零值、可选规则及对象填充边界。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from types import SimpleNamespace

import wtforms
from wtforms import BooleanField, Form, IntegerField, StringField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional


class FormInput(dict):
    """模拟已声明的多值表单输入，所有值明确提供为列表。"""

    def getlist(self, name):
        """取得本次字段原始输入。@param name 字段名。@return 字符串列表。"""
        return self.get(name, [])


def main() -> None:
    """只处理进程内合成表单和对象。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(wtforms.__file__).resolve() == root / 'library/src/wtforms/__init__.py'}
    task = argv[1]
    if task == 'WF-U01':
        class DataForm(Form):
            """以数据真假验必填的合成数量表单。"""
            count = IntegerField(validators=[DataRequired()])

        class InputForm(Form):
            """以输入存在性验必填的合成数量表单。"""
            count = IntegerField(validators=[InputRequired()])

        data, submitted = DataForm(FormInput(count=['0'])), InputForm(FormInput(count=['0']))
        initial = InputForm(data={'count': 3})
        result['required_input_and_truthy_converted_data_are_distinct'] = (
            data.count.data == submitted.count.data == 0 and not data.validate()
            and submitted.validate() and not initial.validate())
    elif task == 'WF-U02':
        class CheckboxForm(Form):
            """用于区分初始显示和缺少勾选提交。"""
            enabled = BooleanField()

        obj = SimpleNamespace(enabled=True)
        initial, submitted = CheckboxForm(obj=obj), CheckboxForm(FormInput(), obj=obj)
        result['missing_checkbox_submission_is_not_the_initial_object_value'] = (
            initial.enabled.data is True and initial.enabled.raw_data is None
            and submitted.enabled.data is False and submitted.enabled.raw_data == [])
    elif task == 'WF-C01':
        class QuantityForm(Form):
            """用于核输入协议和实际类型转换。"""
            count = IntegerField()

        failure = None
        try:
            QuantityForm(formdata={'count': '3'})
        except TypeError as error:
            failure = str(error)
        accepted = QuantityForm(FormInput(count=['3']))
        result['submitted_input_requires_a_multivalue_getlist_protocol'] = (
            failure == "formdata should be a multidict-type wrapper that supports the 'getlist' method"
            and accepted.count.data == 3 and accepted.count.raw_data == ['3'])
    elif task == 'WF-C02':
        class OptionalQuantity(Form):
            """显式保留Optional对原始提交存在性的既有语义。"""
            count = IntegerField(validators=[Optional(), NumberRange(min=0)])

        initial = OptionalQuantity(data={'count': -1})
        submitted = OptionalQuantity(FormInput(count=['-1']))
        result['optional_checks_raw_submission_instead_of_validating_all_initial_values'] = (
            initial.count.data == submitted.count.data == -1
            and initial.validate() and not submitted.validate()
            and initial.count.raw_data is None and submitted.count.raw_data == ['-1'])
    elif task == 'WF-P01':
        class OutputForm(Form):
            """两个字段按声明顺序填充。"""
            first = StringField()
            second = StringField()

        class Output:
            """第二个属性拒绝写入的合成对象。"""
            first = 'old'

            @property
            def second(self):
                """读取原有第二值。@return 原值。"""
                return 'original'

            @second.setter
            def second(self, value):
                """模拟对象拒绝赋值。@param value 待写值。@return 不返回，抛ValueError。"""
                raise ValueError('synthetic setter rejected')

        form = OutputForm(data={'first': 'new', 'second': 'changed'})
        target = Output()
        valid = form.validate()
        rejected = False
        try:
            form.populate_obj(target)
        except ValueError:
            rejected = True
        result['validation_does_not_make_sequential_object_population_atomic'] = (
            valid and rejected and target.first == 'new' and target.second == 'original')
    elif task == 'WF-D01':
        calls = []

        class SharedForm(Form):
            """公开钩子用于核调用方列表所有权。"""
            name = StringField()

            def filter_name(self, value):
                """记录一次内联过滤。@param value 当前值。@return 添加标记的值。"""
                calls.append('filter')
                return value + '!'

            def validate_name(self, field):
                """记录一次内联验证。@param field 当前字段。@return None。"""
                calls.append('validate')

        filters, validators = {'name': []}, {'name': []}
        first = SharedForm(data={'name': 'x'}, extra_filters=filters)
        second = SharedForm(data={'name': 'x'}, extra_filters=filters)
        first.validate(extra_validators=validators)
        first.validate(extra_validators=validators)
        result.update(filter_list_length=len(filters['name']), validator_list_length=len(validators['name']),
            filtered_values=[first.name.data, second.name.data], calls=calls)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
