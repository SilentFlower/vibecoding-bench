"""冻结解析后再打开输出的参考，以及拒绝同路径的部分修复反例。"""
from pathlib import Path
from shutil import copyfile, copytree


def main() -> None:
    """从固定seed制作实际独立候选，不修改原始C或测试入口。@return None。"""
    workspace = Path('.deploy/project-catalog-hundred/stage-02')
    seed = workspace / 'drafts/projects/simplejson/seed'
    reference = workspace / 'references/simplejson'
    wrong = workspace / 'wrong-candidates/simplejson-refuse-inplace'
    original = workspace / 'public-test-controls/simplejson-original'
    for target in (reference, wrong, original):
        copytree(seed, target)
        copyfile(Path(__file__).with_name('simplejson-public-tests.py'), target / 'app/test_tool_output.py')
    relative = 'library/simplejson/tool.py'
    text = (reference / relative).read_text()
    opening = "        outfile = open(sys.argv[2], 'w')"
    writing = '    with outfile:\n'
    if text.count(opening) != 1 or text.count(writing) != 1:
        raise ValueError('固定CLI文件打开或写入位置已变化')
    text = text.replace(opening, '        outfile = None')
    text = text.replace(writing, '    if outfile is None:\n'
        '        # 输入已完整解析并关闭后再打开，避免错误输入和同路径提前截断。\n'
        "        outfile = open(sys.argv[2], 'w')\n" + writing)
    (reference / relative).write_text(text)
    boundary = 'def main():\n'
    if text.count(boundary) != 1:
        raise ValueError('固定CLI主入口已变化')
    (wrong / relative).write_text(text.replace(boundary, boundary
        + '    if len(sys.argv) == 3 and sys.argv[1] == sys.argv[2]:\n'
        + "        raise SystemExit('same path unsupported')\n"))
    print('已冻结真实CLI参考、拒绝同路径的部分修复反例及四项双引擎公开测试。')


if __name__ == '__main__':
    main()
