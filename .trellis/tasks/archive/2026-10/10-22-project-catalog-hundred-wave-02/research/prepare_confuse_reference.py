"""冻结单来源替换参考及过早清空导致错误时丢值的反例。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """从原始seed生成独立两文件候选，不修改原生测试。@return None。"""
    workspace = Path('.deploy/project-catalog-hundred/stage-02')
    seed = workspace / 'drafts/projects/confuse/seed'
    reference = workspace / 'references/confuse'
    wrong = workspace / 'wrong-candidates/confuse-clear-before-parse'
    original = workspace / 'public-test-controls/confuse-original'
    for target in (reference, wrong, original):
        copytree(seed, target)
        copyfile(Path(__file__).with_name('confuse-public-tests.py'), target / 'app/test_reload.py')
    relative = 'library/confuse/sources.py'
    text = (reference / relative).read_text()
    old = '        if isinstance(value, dict):\n            self.update(value)'
    if text.count(old) != 1:
        raise ValueError('固定YamlSource发布位置已变化')
    replacement = ('        if isinstance(value, dict):\n'
        '            # 只有完整解析并确认映射后才替换，失败保留此前有效来源。\n'
        '            self.clear()\n            self.update(value)')
    (reference / relative).write_text(text.replace(old, replacement))
    boundary = '        if self.optional and (\n'
    if text.count(boundary) != 1:
        raise ValueError('固定文件源读取边界已变化')
    (wrong / relative).write_text(text.replace(boundary, '        self.clear()\n' + boundary))
    print('已冻结单文件源参考、解析前清空反例和四项公开回归原版控制。')


if __name__ == '__main__':
    main()
