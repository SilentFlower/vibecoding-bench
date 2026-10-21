"""制作Click附注增强参考、父类单路径反例和原版公开测试控制。"""
from pathlib import Path
from shutil import copytree


WORKSPACE = Path.cwd() / '.deploy/project-catalog-hundred/stage-01'
TESTS = '''"""受控错误附注的公开原版失败回归。"""
from io import StringIO

import click
from click.testing import CliRunner


def test_order_error_notes_display_and_unnoted_control():
    """基础错误须输出有序附注而不改变主消息或普通错误。@return None。"""
    error = click.ClickException("Order unavailable")
    error.add_note("Check local input")
    error.add_note("")
    error.add_note("咖啡\\nsecond line")
    output = StringIO()
    error.show(file=output)
    assert output.getvalue() == "Error: Order unavailable\\nNote: Check local input\\nNote: 咖啡\\nsecond line\\n"
    assert error.format_message() == "Order unavailable"
    plain = StringIO()
    click.ClickException("plain").show(file=plain)
    assert plain.getvalue() == "Error: plain\\n"


def test_order_usage_notes_keep_exit_and_usage():
    """UsageError覆盖路径也必须展示附注，usage和退出码保持。@return None。"""
    @click.command()
    def ship():
        """产生合成参数错误。@return None。"""
        error = click.UsageError("Invalid order", ctx=click.get_current_context())
        error.add_note("Check quantity")
        raise error

    result = CliRunner().invoke(ship)
    assert result.exit_code == 2
    assert result.stderr.count("Usage:") == 1
    assert result.stderr.endswith("Error: Invalid order\\nNote: Check quantity\\n")
'''


def enhance(source: str, *, usage: bool) -> str:
    """按已读真实方法添加附注。@param source 原文。@param usage 是否含子类路径。@return 参考原文。"""
    colors = ['self.show_color', 'color'] if usage else ['self.show_color']
    for color in colors:
        anchor = ('        echo(\n            _("Error: {message}").format(message=self.format_message()),\n'
            '            file=file,\n            color=' + color + ',\n        )\n')
        if source.count(anchor) != 1:
            raise ValueError('附注增强锚点与已读方法不符')
        source = source.replace(anchor, anchor +
            '        for note in getattr(self, "__notes__", ()):\n'
            '            if note:\n'
            '                echo(_("Note: {note}").format(note=note), file=file, color=' + color + ')\n')
    return source


def main() -> None:
    """保留原版，参考和反例只改变明确授权文件。@return None。"""
    seed = WORKSPACE / 'drafts/projects/click/seed'
    reference = WORKSPACE / 'references/click'
    original_control = WORKSPACE / 'public-test-controls/click-original'
    wrong = WORKSPACE / 'wrong-candidates/click-base-notes-only'
    for path in (reference, original_control, wrong):
        if path.exists():
            raise ValueError('参考或控制不允许覆盖')
    copytree(seed, reference)
    module = reference / 'library/src/click/exceptions.py'
    original = module.read_text(encoding='utf-8')
    reference_text = enhance(original, usage=True)
    signature = '    def show(self, file: t.IO[t.Any] | None = None) -> None:\n        if file is None:\n'
    if reference_text.count(signature) != 2:
        raise ValueError('公开show签名数量与已读源码不一致')
    reference_text = reference_text.replace(signature,
        '    def show(self, file: t.IO[t.Any] | None = None) -> None:\n'
        '        """显示受控错误与有序附注。@param file 输出流。@return None。"""\n'
        '        if file is None:\n')
    module.write_text(reference_text, encoding='utf-8')
    test_path = 'library/tests/test_exceptions/test_click_exception.py'
    (reference / test_path).write_text(TESTS, encoding='utf-8')
    copytree(seed, original_control)
    (original_control / test_path).write_text(TESTS, encoding='utf-8')
    copytree(reference, wrong)
    (wrong / 'library/src/click/exceptions.py').write_text(enhance(original, usage=False), encoding='utf-8')
    print('Click参考、两条公开测试、原版控制和仅父类修复反例已制作。')


if __name__ == '__main__':
    main()
