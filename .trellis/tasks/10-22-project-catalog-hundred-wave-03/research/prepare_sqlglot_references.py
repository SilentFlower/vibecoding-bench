"""按已核原文建立血缘渲染参考、错误候选及公开测试原版控制。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """仅修改两个授权文件，不覆盖旧原件。@return None。"""
    root = Path.cwd()
    work = root / '.deploy/project-catalog-hundred/stage-03'
    research = Path(__file__).resolve().parent
    seed = work / 'drafts/projects/sqlglot/seed'
    reference = work / 'references/sqlglot'
    wrong = work / 'wrong-candidates/sqlglot-copy-without-highlight'
    public = work / 'public-test-controls/sqlglot-original'
    for destination in (reference, wrong, public):
        copytree(seed, destination)
        copyfile(research / 'sqlglot-public-tests.py', destination / 'app/test_lineage_render.py')
    path = Path('library/sqlglot/lineage.py')
    original = (seed / path).read_text()
    old = '''                source = node.source.transform(
                    lambda n: (
                        exp.Tag(this=n, prefix="<b>", postfix="</b>") if n is node.expression else n
                    ),
                    copy=False,
                ).sql(pretty=True, dialect=dialect)'''
    new = '''                source = node.source.copy()
                # 原高亮按对象身份匹配；逐一映射复制节点，既保护原树又保留对应高亮。
                target = next(
                    (cloned for original, cloned in zip(node.source.walk(), source.walk())
                     if original is node.expression),
                    None,
                )
                source = source.transform(
                    lambda n: (
                        exp.Tag(this=n, prefix="<b>", postfix="</b>") if n is target else n
                    ),
                    copy=False,
                ).sql(pretty=True, dialect=dialect)'''
    assert original.count(old) == 1
    (reference / path).write_text(original.replace(old, new))
    (wrong / path).write_text(original.replace(old, old.replace('copy=False', 'copy=True')))
    print({'reference': str(reference.relative_to(root)), 'wrong': str(wrong.relative_to(root)),
        'public_tests': 6, 'authorized_files': [str(path), 'app/test_lineage_render.py']})


if __name__ == '__main__':
    main()
