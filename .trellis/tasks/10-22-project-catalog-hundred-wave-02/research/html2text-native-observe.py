"""核文档结构、图像策略、回调、字符表示和逐文档状态归属。"""
import json
import os
from pathlib import Path
import sys

import html2text
from html2text import HTML2Text


def main() -> None:
    """只转换完整本地合成HTML，不抓取资源。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(html2text.__file__).resolve() == root / 'library/html2text/__init__.py'}
    task = sys.argv[1]
    if task == 'HT-U01':
        converter = HTML2Text(baseurl='https://docs.example.test/team/', bodywidth=0)
        output = converter.handle('<h1>Report</h1><p><strong>Done</strong> <a href="guide.md">Guide</a></p><ol start="3"><li>A</li><li>B</li></ol>')
        result['local_html_conversion_preserves_headings_emphasis_links_and_list_start'] = (
            '# Report' in output and '**Done**' in output
            and '[Guide](https://docs.example.test/team/guide.md)' in output
            and '3. A' in output and '4. B' in output)
    elif task == 'HT-U02':
        source = '<p>A<img src="figure.png" alt="Revenue chart">B</p>'
        ordinary = HTML2Text(bodywidth=0).handle(source)
        alt_converter, ignore_converter = HTML2Text(bodywidth=0), HTML2Text(bodywidth=0)
        alt_converter.images_to_alt = True
        ignore_converter.ignore_images = True
        alt, ignored = alt_converter.handle(source), ignore_converter.handle(source)
        result['image_alt_retention_and_omission_are_distinct_existing_policies'] = (
            '![Revenue chart](figure.png)' in ordinary
            and 'Revenue chart' in alt and '![' not in alt and 'figure.png' not in alt
            and 'Revenue chart' not in ignored and 'figure.png' not in ignored)
    elif task == 'HT-C01':
        converter = HTML2Text(bodywidth=0)
        events = []

        def callback(instance, tag, attrs, start):
            """记录回调并用现有返回值覆盖标题默认分派。@return 是否已处理该标签。"""
            events.append((tag, start))
            if tag == 'h1':
                if start:
                    instance.o('TITLE: ')
                return True
            return False

        converter.tag_callback = callback
        output = converter.handle('<h1>Report</h1><p><strong>Done</strong></p>')
        result['tag_callback_can_replace_selected_tag_dispatch_and_retain_other_defaults'] = (
            'TITLE: Report' in output and '# Report' not in output and '**Done**' in output
            and ('h1', True) in events and ('h1', False) in events)
    elif task == 'HT-C02':
        source = '<p>A&nbsp;B &copy;</p><script>secret</script><style>.x{color:red}</style>'
        ordinary = HTML2Text(bodywidth=0).handle(source)
        converter = HTML2Text(bodywidth=0)
        converter.unicode_snob = True
        preserved = converter.handle(source)
        result['unicode_policy_changes_nbsp_and_entity_representation_without_lossless_roundtrip'] = (
            'A B (C)' in ordinary and 'A\u00a0B ©' in preserved
            and 'secret' not in ordinary + preserved and 'color:red' not in ordinary + preserved)
    elif task == 'HT-P01':
        converter = HTML2Text(bodywidth=0)
        first = converter.handle('<script>hidden')
        second = converter.handle('<p>Visible</p>')
        fresh = HTML2Text(bodywidth=0).handle('<p>Visible</p>')
        result['unfinished_quiet_state_can_cross_document_calls_and_fresh_instances_isolate_it'] = (
            first.strip() == '' and 'Visible' not in second and 'Visible' in fresh and converter.quiet == 1)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
