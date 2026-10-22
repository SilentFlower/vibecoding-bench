"""以固定转换器观察标签、表格、图片、代码块和配置缓存。"""
from contextlib import redirect_stdout
from io import StringIO
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from tempfile import TemporaryDirectory

import markdownify
from markdownify import MarkdownConverter, markdownify as convert
from markdownify.main import main as cli_main


def main() -> None:
    """仅转换合成HTML，不写候选源码。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(markdownify.__file__).resolve() == root / 'library/markdownify/__init__.py'}
    task = argv[1]
    if task == 'MD-U01':
        html = '<p>Hello <strong>paid <em>today</em></strong></p>'
        result['strip_removes_tag_conversion_and_preserves_children'] = (
            convert(html, strip=['strong']) == 'Hello paid *today*'
            and convert('<script>window.secret=7</script>') == ''
            and convert('<script>window.secret=7</script>', strip=['script']) == 'window.secret=7')
    elif task == 'MD-U02':
        html = '<table><tr><td>tea</td><td>3</td></tr><tr><td>book</td><td>8</td></tr></table>'
        default = convert(html)
        inferred = convert(html, table_infer_header=True)
        result['header_inference_reclassifies_the_first_data_row'] = (
            default == '|  |  |\n| --- | --- |\n| tea | 3 |\n| book | 8 |'
            and inferred == '| tea | 3 |\n| --- | --- |\n| book | 8 |')
    elif task == 'MD-C01':
        html = '<h2><img src="chart.png" alt="Revenue"></h2>'
        normal = convert(html, heading_style='ATX')
        kept = convert(html, heading_style='ATX', keep_inline_images_in=['h2'])
        result['inline_image_policy_depends_on_parent_tag'] = (
            normal == '## Revenue' and kept == '## ![Revenue](chart.png)'
            and convert('<p><img src="chart.png" alt="Revenue"></p>') == '![Revenue](chart.png)')
    elif task == 'MD-C02':
        html = '<pre class="language-python">\n  print(1)\n\n</pre>'
        fallback = convert(html, code_language='text', code_language_callback=lambda element: None)
        chosen = convert(html, code_language='text', code_language_callback=lambda element: element['class'][0][9:])
        preserved = convert(html, code_language='text', strip_pre=None)
        result['code_language_callback_falls_back_and_whitespace_is_explicit'] = (
            fallback == '```text\n  print(1)\n```'
            and chosen == '```python\n  print(1)\n```'
            and preserved == '```text\n\n  print(1)\n\n\n```')
    elif task == 'MD-P01':
        html = '<a href="https://example.test">https://example.test</a>'
        with TemporaryDirectory(dir='/tmp') as temporary:
            source = Path(temporary) / 'input.html'
            source.write_text(html)
            default, explicit = StringIO(), StringIO()
            with redirect_stdout(default):
                cli_main([str(source)])
            with redirect_stdout(explicit):
                cli_main(['--autolinks', '--default-title', str(source)])
        result['cli_defaults_and_print_newline_require_an_explicit_export_profile'] = (
            convert(html) == '<https://example.test>'
            and default.getvalue() == '[https://example.test](https://example.test "https://example.test")\n'
            and explicit.getvalue() == convert(html) + '\n')
    elif task == 'MD-D01':
        html = '<strong>paid</strong>'
        reused = MarkdownConverter()
        first = reused.convert(html)
        reused.options['strip'] = ['strong']
        result.update(first=first, reused_after_option_change=reused.convert(html),
            fresh_with_strip=MarkdownConverter(strip=['strong']).convert(html))
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
