"""制作falsey key修复、漏掉分组的反例及原版公开测试控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''

def test_redundant_uses_falsey_callable_business_key():
    """可调用对象的自身真值不得取消归一化。@return None。"""
    class FalseKey:
        """模拟falsey业务键函数。"""

        def __call__(self, value):
            """归一化业务值。@param value 原值。@return 小写键。"""
            return value.lower()

        def __bool__(self):
            """保持自身falsey。@return False。"""
            return False

    assert redundant(['A', 'a', 'B', 'b'], key=FalseKey()) == ['a', 'b']


def test_redundant_grouped_records_use_zero_length_callable():
    """分组与不可哈希记录同样须使用合法key。@return None。"""
    class EmptyKey:
        """模拟长度为零的记录键函数。"""

        def __call__(self, value):
            """归一化真实记录字段。@param value 记录。@return 小写键。"""
            return value['code'].lower()

        def __len__(self):
            """保持零长度。@return 0。"""
            return 0

    rows = [{'code': 'A'}, {'code': 'a'}, {'code': 'B'}, {'code': 'b'}]
    assert redundant(rows, key=EmptyKey(), groups=True) == [[rows[0], rows[1]], [rows[2], rows[3]]]
    assert rows == [{'code': 'A'}, {'code': 'a'}, {'code': 'B'}, {'code': 'b'}]
'''


def main() -> None:
    """只改变两个授权文件，完整原版和失败对照保留。@return None。"""
    seed = WORKSPACE / 'drafts/projects/boltons/seed'
    reference = WORKSPACE / 'references/boltons'
    control = WORKSPACE / 'public-test-controls/boltons-original'
    wrong = WORKSPACE / 'wrong-candidates/boltons-ungrouped-only'
    for path in (reference, control, wrong):
        if path.exists():
            raise ValueError('既有参考不允许覆盖')
    copytree(seed, reference)
    module = reference / 'library/boltons/iterutils.py'
    original = module.read_text(encoding='utf-8')
    anchor = '        k = key_func(i) if key else i\n'
    if original.count(anchor) != 1:
        raise ValueError('归一化执行锚点与实际源码不一致')
    module.write_text(original.replace(anchor,
        '        # 合法key的存在性不能由对象自身的布尔值决定。\n'
        '        k = key_func(i) if key is not None else i\n'), encoding='utf-8')
    tests = reference / 'library/tests/test_iterutils.py'
    previous = tests.read_text(encoding='utf-8')
    import_anchor = 'from boltons.dictutils import OMD\n'
    if previous.count(import_anchor) != 1:
        raise ValueError('公开测试导入锚点与实际源码不一致')
    tests.write_text(previous.replace(import_anchor,
        import_anchor + 'from boltons.iterutils import redundant\n') + TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/tests/test_iterutils.py').write_text(tests.read_text(encoding='utf-8'), encoding='utf-8')
    copytree(reference, wrong)
    (wrong / 'library/boltons/iterutils.py').write_text(original.replace(anchor,
        '        k = key_func(i) if (key is not None and not groups) or key else i\n'), encoding='utf-8')
    print('Boltons参考、两条公开测试、原版控制和仅非分组修复反例已制作。')


if __name__ == '__main__':
    main()
