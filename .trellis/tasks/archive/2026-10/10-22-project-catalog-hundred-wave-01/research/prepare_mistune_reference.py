"""制作空文档CLI参考、跳过输出反例与原版公开测试控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''

def test_empty_message_and_piped_document_are_valid():
    """已提供空文本与没有输入必须区分。@return None。"""
    for arguments in ([], ["-m", ""]):
        result = subprocess.run([sys.executable, "-m", "mistune", *arguments],
            input="", text=True, capture_output=True, timeout=8)
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert result.stderr == ""


def test_empty_message_writes_file_and_wins_over_file_input(tmp_path):
    """空结果仍应写文件，并保留显式消息优先。@param tmp_path 临时目录。@return None。"""
    destination = tmp_path / "result.html"
    output = subprocess.run([sys.executable, "-m", "mistune", "-m", "", "-o", str(destination)],
        input="", text=True, capture_output=True, timeout=8)
    assert output.returncode == 0
    assert destination.is_file() and destination.read_text() == ""
    assert output.stdout == ""
    document = tmp_path / "source.md"
    document.write_text("# File fallback", encoding="utf-8")
    priority = subprocess.run([sys.executable, "-m", "mistune", "-m", "", "-f", str(document)],
        input="", text=True, capture_output=True, timeout=8)
    assert priority.returncode == 0
    assert priority.stdout.strip() == ""
'''


def main() -> None:
    """只修改两个授权文件，保留原版节点和完整候选。@return None。"""
    seed = WORKSPACE / 'drafts/projects/mistune/seed'
    reference = WORKSPACE / 'references/mistune'
    control = WORKSPACE / 'public-test-controls/mistune-original'
    wrong = WORKSPACE / 'wrong-candidates/mistune-empty-return'
    for path in (reference, control, wrong):
        if path.exists():
            raise ValueError('既有参考和控制不允许覆盖')
    copytree(seed, reference)
    module = reference / 'library/src/mistune/__main__.py'
    original = module.read_text(encoding='utf-8')
    first, second = '    if not message and not args.file:\n', '    if message:\n'
    if original.count(first) != 1 or original.count(second) != 1:
        raise ValueError('CLI分派锚点与已读源码不一致')
    enhanced = original.replace(first, '    if message is None and not args.file:\n')
    enhanced = enhanced.replace(second, '    if message is not None:\n')
    module.write_text(enhanced, encoding='utf-8')
    tests = reference / 'library/tests/test_cli.py'
    previous = tests.read_text(encoding='utf-8')
    if previous.count('import io\n') != 1:
        raise ValueError('公开测试导入锚点不符')
    tests.write_text(previous.replace('import io\n', 'import io\nimport subprocess\n') + TESTS, encoding='utf-8')
    copytree(seed, control)
    (control / 'library/tests/test_cli.py').write_text(tests.read_text(encoding='utf-8'), encoding='utf-8')
    copytree(reference, wrong)
    (wrong / 'library/src/mistune/__main__.py').write_text(enhanced.replace('    if message is not None:\n',
        '    if message == "":\n        return\n    if message is not None:\n'), encoding='utf-8')
    print('Mistune参考、两条公开测试、原版控制和空输入直接返回反例已制作。')


if __name__ == '__main__':
    main()
