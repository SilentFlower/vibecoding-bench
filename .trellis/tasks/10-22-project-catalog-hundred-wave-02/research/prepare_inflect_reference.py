"""准备未知模式键预校验参考和只保护all路径的错误候选。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """从完整seed创建独立原版公开控制及两份候选。@return None。"""
    work = Path('.deploy/project-catalog-hundred/stage-02')
    seed = work / 'drafts/projects/inflect/seed'
    reference = work / 'references/inflect'
    copytree(seed, reference)
    relative = 'library/inflect/__init__.py'
    path = reference / relative
    text = path.read_text()
    marker = '        if not kwargs:\n            self.classical_dict = all_classical.copy()'
    if text.count(marker) != 1:
        raise ValueError('原生classical入口定位不唯一')
    guard = ('        # 先验证全部键，避免抛错前改变后续文案使用的模式。\n'
        '        if any(key not in def_classical for key in kwargs):\n'
        '            raise UnknownClassicalModeError\n')
    path.write_text(text.replace(marker, guard + marker))
    copyfile(Path(__file__).with_name('inflect-public-tests.py'), reference / 'app/test_classical.py')
    fragment = reference / 'library/newsfragments/+classical-validation.bugfix.rst'
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text('Validate all classical mode keys before changing engine state.\n')
    wrong = work / 'wrong-candidates/inflect-guard-all-only'
    copytree(reference, wrong)
    (wrong / relative).write_text(text.replace(marker, guard.replace('if any(', 'if "all" in kwargs and any(') + marker))
    control = work / 'public-test-controls/inflect-original'
    copytree(seed, control)
    copyfile(reference / 'app/test_classical.py', control / 'app/test_classical.py')
    print('inflect reference and negative controls frozen')


if __name__ == '__main__':
    main()
