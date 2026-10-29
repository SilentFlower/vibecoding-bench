"""制作tuple排版修复、只修单一路径的反例及公开测试原版控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''

def test_inventory_rowalign_tuple_equivalence():
    """短tuple与list必须等价且不得修改调用方。@return None。"""
    rows = [["coffee\\nbeans", "ready"], ["tea", "packed"]]
    options = {"headers": ["Product name", "Shipping note"], "tablefmt": "grid"}
    value = ["bottom"]
    assert tabulate(rows, rowalign=("bottom",), **options) == tabulate(rows, rowalign=value, **options)
    assert tabulate(rows, rowalign=(), **options) == tabulate(rows, rowalign=[], **options)
    assert value == ["bottom"]


def test_inventory_headerwidth_tuple_equivalence():
    """表头宽度也必须走同一合法序列合同。@return None。"""
    rows = [["coffee", "ready"], ["tea", "packed"]]
    options = {"headers": ["Product name", "Shipping note"], "tablefmt": "grid"}
    value = [6]
    assert tabulate(rows, maxheadercolwidths=(6,), **options) == tabulate(rows, maxheadercolwidths=value, **options)
    assert tabulate(rows, maxheadercolwidths=(), **options) == tabulate(rows, maxheadercolwidths=[], **options)
    assert value == [6]
'''


def main() -> None:
    """保留原版所有文件，只在参考中修改两个授权文件。@return None。"""
    seed = WORKSPACE / 'drafts/projects/tabulate/seed'
    reference = WORKSPACE / 'references/tabulate'
    control = WORKSPACE / 'public-test-controls/tabulate-original'
    wrong = WORKSPACE / 'wrong-candidates/tabulate-rowalign-only'
    for path in (reference, control, wrong):
        if path.exists():
            raise ValueError('既有参考不允许覆盖')
    copytree(seed, reference)
    module = reference / 'library/tabulate/__init__.py'
    original = module.read_text(encoding='utf-8')
    anchor = '    if isinstance(original, Iterable) and not isinstance(original, str):\n'
    if original.count(anchor) != 1:
        raise ValueError('原版参数展开锚点与已读源码不一致')
    replacement = ('    # tuple与list采用同一补齐运算，同时避免修改调用方序列。\n'
        '    if isinstance(original, tuple):\n        original = list(original)\n' + anchor)
    module.write_text(original.replace(anchor, replacement), encoding='utf-8')
    tests = reference / 'library/test/test_api.py'
    tests.write_text(tests.read_text(encoding='utf-8') + TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/test/test_api.py').write_text(tests.read_text(encoding='utf-8'), encoding='utf-8')
    copytree(reference, wrong)
    narrow = '    list_of_lists, headers, headers_pad = _normalize_tabular_data(\n'
    if original.count(narrow) != 1:
        raise ValueError('错误候选入口锚点不一致')
    (wrong / 'library/tabulate/__init__.py').write_text(original.replace(narrow,
        '    if isinstance(rowalign, tuple):\n        rowalign = list(rowalign)\n' + narrow), encoding='utf-8')
    print('Tabulate参考、两条公开测试、原版控制和单路径反例已制作。')


if __name__ == '__main__':
    main()
