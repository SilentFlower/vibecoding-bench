"""冻结数组外观文本禁用参考和关闭默认检测的独立反例。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """只修改授权分派条件与公开测试。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-02')
    seed = work / 'drafts/projects/xlsxwriter/seed'
    reference = work / 'references/xlsxwriter'
    copytree(seed, reference)
    relative = 'library/xlsxwriter/worksheet.py'
    path = reference / relative
    text = path.read_text()
    marker = '        if token.startswith("{=") and token.endswith("}"):\n            return self._write_formula(row, col, *args)\n'
    if text.count(marker) != 1:
        raise ValueError('通用数组字符串分派定位不唯一')
    path.write_text(text.replace(marker, marker.replace('if token.startswith', 'if self.strings_to_formulas and token.startswith')))
    copyfile(Path(__file__).with_name('xlsxwriter-public-tests.py'), reference / 'app/test_formula_optout.py')
    wrong = work / 'wrong-candidates/xlsxwriter-disable-array-detection'
    copytree(reference, wrong)
    (wrong / relative).write_text(text.replace(marker, ''))
    control = work / 'public-test-controls/xlsxwriter-original'
    copytree(seed, control)
    copyfile(reference / 'app/test_formula_optout.py', control / 'app/test_formula_optout.py')
    print('xlsxwriter reference and negative controls frozen')


if __name__ == '__main__':
    main()
