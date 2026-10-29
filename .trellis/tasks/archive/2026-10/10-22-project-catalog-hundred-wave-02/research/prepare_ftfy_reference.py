"""冻结完整配置转交参考、单开关错误候选及原版公开测试控制。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """只改变授权源码行和实际公开回归文件。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-02')
    seed = work / 'drafts/projects/ftfy/seed'
    reference = work / 'references/ftfy'
    copytree(seed, reference)
    relative = 'library/ftfy/__init__.py'
    path = reference / relative
    original = path.read_text()
    marker = '                text = fix_encoding(text)\n'
    if original.count(marker) != 1:
        raise ValueError('实际非解释分支定位不唯一')
    path.write_text(original.replace(marker,
        '                # 关闭解释只改变取证开销，仍须完整转交调用方的编码修整政策。\n'
        '                text = fix_encoding(text, config)\n'))
    copyfile(Path(__file__).with_name('ftfy-public-tests.py'), reference / 'app/test_explain_config.py')
    wrong = work / 'wrong-candidates/ftfy-single-option-forwarding'
    copytree(reference, wrong)
    (wrong / relative).write_text(original.replace(marker,
        '                text = fix_encoding(text, TextFixerConfig(decode_inconsistent_utf8=config.decode_inconsistent_utf8))\n'))
    control = work / 'public-test-controls/ftfy-original'
    copytree(seed, control)
    copyfile(reference / 'app/test_explain_config.py', control / 'app/test_explain_config.py')
    print('ftfy参考和独立错误候选已冻结')


if __name__ == '__main__':
    main()
