"""为真实回调缺陷冻结两文件参考、错误句柄反例和原版公开测试控制。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """从固定seed复制独立候选，不改原版或正式内容。@return None。"""
    workspace = Path('.deploy/project-catalog-hundred/stage-02')
    seed = workspace / 'drafts/projects/alive-progress/seed'
    reference = workspace / 'references/alive-progress'
    wrong = workspace / 'wrong-candidates/alive-progress-wrong-handle'
    original = workspace / 'public-test-controls/alive-progress-original'
    for target in (reference, wrong, original):
        copytree(seed, target)
        copyfile(Path(__file__).with_name('alive-progress-public-tests.py'), target / 'app/test_finalize.py')
    relative = 'library/alive_progress/core/progress.py'
    text = (reference / relative).read_text()
    if text.count('if self._finalize:') != 1:
        raise ValueError('固定源码回调选择条件已变化')
    text = text.replace('if self._finalize:', 'if self._finalize is not None:')
    (reference / relative).write_text(text)
    if text.count('self._finalize(self._bar)') != 1:
        raise ValueError('固定源码回调参数已变化')
    (wrong / relative).write_text(text.replace('self._finalize(self._bar)', 'self._finalize(self._it)'))
    print('已冻结独立参考、错误句柄反例和四项公开测试的原版控制。')


if __name__ == '__main__':
    main()
