"""冻结日期拒绝参考及静默截断的独立错误候选。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """只修改授权Date实现与公开测试，原源码保持不变。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-02')
    seed = work / 'drafts/projects/marshmallow/seed'
    reference = work / 'references/marshmallow'
    copytree(seed, reference)
    relative = 'library/src/marshmallow/fields.py'
    path = reference / relative
    original = path.read_text()
    marker = '    SCHEMA_OPTS_VAR_NAME = "dateformat"\n'
    if original.count(marker) != 1:
        raise ValueError('冻结Date定位不唯一')
    addition = '''
    def _deserialize(self, value, attr, data, **kwargs):
        """拒绝时间对象，避免日期合同静默遗失时间。@return 日历日期。"""
        if isinstance(value, dt.datetime):
            raise self.make_error("invalid", input=value)
        return super()._deserialize(value, attr, data, **kwargs)
'''
    path.write_text(original.replace(marker, marker + addition))
    copyfile(Path(__file__).with_name('marshmallow-public-tests.py'), reference / 'app/test_date.py')
    wrong = work / 'wrong-candidates/marshmallow-truncate-datetime'
    copytree(reference, wrong)
    (wrong / relative).write_text(path.read_text().replace('raise self.make_error("invalid", input=value)\n        return super()._deserialize(value, attr, data, **kwargs)', 'return value.date()\n        return super()._deserialize(value, attr, data, **kwargs)'))
    control = work / 'public-test-controls/marshmallow-original'
    copytree(seed, control)
    copyfile(reference / 'app/test_date.py', control / 'app/test_date.py')
    print('marshmallow reference and negative controls frozen')


if __name__ == '__main__':
    main()
