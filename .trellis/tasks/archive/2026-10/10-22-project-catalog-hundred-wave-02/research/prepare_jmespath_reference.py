"""冻结JSON比较参考与只处理数组的真实不完整反例。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """以固定seed生成独立候选与四项公开测试。@return None。"""
    workspace = Path('.deploy/project-catalog-hundred/stage-02')
    seed = workspace / 'drafts/projects/jmespath/seed'
    reference = workspace / 'references/jmespath'
    wrong = workspace / 'wrong-candidates/jmespath-arrays-only'
    original = workspace / 'public-test-controls/jmespath-original'
    for target in (reference, wrong, original):
        copytree(seed, target)
        copyfile(Path(__file__).with_name('jmespath-public-tests.py'), target / 'app/test_json_equality.py')
    path = 'library/jmespath/visitor.py'
    text = (reference / path).read_text()
    start = text.index('def _equals(x, y):')
    end = text.index('\ndef _is_special_number_case', start)
    arrays = ('def _equals(x, y):\n'
        '    if _is_special_number_case(x, y):\n        return False\n'
        '    if isinstance(x, list) and isinstance(y, list):\n'
        '        return len(x) == len(y) and all(_equals(a, b) for a, b in zip(x, y))\n')
    objects = ('    if isinstance(x, dict) and isinstance(y, dict):\n'
        '        # Python容器比较会混淆布尔和数字，成员必须继续使用JSON相等规则。\n'
        '        return x.keys() == y.keys() and all(_equals(x[key], y[key]) for key in x)\n')
    (reference / path).write_text(text[:start] + arrays + objects + '    return x == y\n\n' + text[end:])
    (wrong / path).write_text(text[:start] + arrays + '    return x == y\n\n' + text[end:])
    print('已冻结递归比较参考、数组局部修复反例和原版公开测试控制。')


if __name__ == '__main__':
    main()
