"""核真实Markdown插件的token、渲染与每文档状态。"""
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys

from markdown_it import MarkdownIt
import mdit_py_plugins
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.gfm import gfm_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
import yaml


class Inputs(HTMLParser):
    """独立读取生成控件的属性。"""

    def __init__(self, html: str):
        """解析本地HTML。@param html 原生输出。@return None。"""
        super().__init__()
        self.inputs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        """记录输入控件。@param tag 标签。@param attrs 属性。@return None。"""
        if tag == 'input':
            self.inputs.append(dict(attrs))


def main() -> None:
    """核完整合成输入及现有配置，不启动浏览器脚本。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(mdit_py_plugins.__file__).resolve() == root / 'library/mdit_py_plugins/__init__.py'}
    task = sys.argv[1]
    if task == 'MD-U01':
        parser = MarkdownIt('commonmark').use(front_matter_plugin)
        env = {}
        tokens = parser.parse('---\ntitle: Local\npublished: false\n---\n\n# Body\n', env)
        front = [token for token in tokens if token.type == 'front_matter']
        html = parser.renderer.render(tokens, parser.options, env)
        result['one_parse_preserves_hidden_raw_front_matter_for_explicit_metadata_loading'] = (
            len(front) == 1 and front[0].hidden and front[0].map == [0, 4]
            and front[0].content == 'title: Local\npublished: false'
            and yaml.safe_load(front[0].content) == {'title': 'Local', 'published': False}
            # 隐藏块保留一个呈现换行；业务要求正文与元数据分离，不约束首尾空白。
            and env == {} and html.strip() == '<h1>Body</h1>')
    elif task == 'MD-U02':
        parser = MarkdownIt('commonmark').use(anchors_plugin)
        tokens = parser.parse('# Same\n\n# Same\n\n### Deep\n', {})
        headers = [token for token in tokens if token.type == 'heading_open']
        again = [token for token in parser.parse('# Same\n', {}) if token.type == 'heading_open']
        result['anchor_uniqueness_is_per_parse_and_default_levels_stop_at_two'] = (
            [token.attrGet('id') for token in headers] == ['same', 'same-1', None]
            and again[0].attrGet('id') == 'same')
    elif task == 'MD-C01':
        source = '- [ ] pending\n- [x] done\n'
        default = MarkdownIt('commonmark', {'html': False}).use(tasklists_plugin).render(source)
        editable = MarkdownIt('commonmark', {'html': False}).use(tasklists_plugin, enabled=True).render(source)
        first, second = Inputs(default).inputs, Inputs(editable).inputs
        result['enabled_option_changes_checkbox_interaction_without_providing_persistence'] = (
            len(first) == len(second) == 2 and all('disabled' in item for item in first)
            and all('disabled' not in item for item in second)
            and ['checked' in item for item in first] == [False, True]
            and ['checked' in item for item in second] == [False, True])
    elif task == 'MD-C02':
        source = 'Ref[^a] again[^a].\n\n[^a]: Used note\n\n[^unused]: OMIT_THIS_NOTE\n'
        parser = MarkdownIt('commonmark').use(footnote_plugin)
        tokens = parser.parse(source, {})
        opened = [token for token in tokens if token.type == 'footnote_open']
        backlinks = [token for token in tokens if token.type == 'footnote_anchor']
        html = parser.renderer.render(tokens, parser.options, {})
        inline = parser.render('Inline ^[LOCAL_INLINE].\n')
        literal = MarkdownIt('commonmark').use(footnote_plugin, inline=False).render('Inline ^[LOCAL_INLINE].\n')
        result['footnotes_render_only_referenced_definitions_with_backlinks_and_configurable_inline_syntax'] = (
            len(opened) == 1 and len(backlinks) == 2 and opened[0].meta['label'] == 'a'
            and 'Used note' in html and 'OMIT_THIS_NOTE' not in html
            and 'footnote-ref' in inline and 'footnote-ref' not in literal and '^[LOCAL_INLINE]' in literal)
    elif task == 'MD-P01':
        source = '<script>LOCAL_TEXT</script>\n\n- [x] done\n'
        raw = MarkdownIt('commonmark', {'html': True}).use(gfm_plugin).render(source)
        escaped = MarkdownIt('commonmark', {'html': False}).use(gfm_plugin).render(source)
        result['gfm_composition_is_not_html_tag_filtering_and_raw_html_policy_is_explicit'] = (
            '<script>LOCAL_TEXT</script>' in raw and '<script>' not in escaped
            and '&lt;script&gt;LOCAL_TEXT&lt;/script&gt;' in escaped
            and len(Inputs(raw).inputs) == len(Inputs(escaped).inputs) == 1)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
