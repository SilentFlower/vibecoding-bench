"""观察真实Token行映射、linkify规则、渲染回调和引用env。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import markdown_it
from markdown_it import MarkdownIt


def token_maps() -> dict:
    """核块与行内token的实际层次，不推断未提供的字符位置。@return token事实。"""
    tokens = MarkdownIt().parse('# Orders\n\nTea **hot**\n')
    heading = tokens[0]
    paragraph = next(token for token in tokens if token.type == 'paragraph_open')
    inline = next(token for token in tokens if token.type == 'inline' and token.content == 'Tea **hot**')
    child_types = [child.type for child in inline.children]
    return {'block_and_inline_token_layers_are_distinct': heading.type == 'heading_open' and heading.nesting == 1
            and tokens[2].type == 'heading_close' and tokens[2].nesting == -1
            and 'strong_open' in child_types and 'strong_close' in child_types,
        'source_maps_are_line_ranges': heading.map == [0, 1] and paragraph.map == [2, 3]
            and inline.map == [2, 3] and all(child.map is None for child in inline.children)}


def linkification() -> dict:
    """对照选项与规则启用的两个真实条件。@return URL处理事实。"""
    source = 'Visit https://example.org/shop.'
    parser = MarkdownIt('commonmark', {'linkify': True})
    before = parser.render(source)
    inactive = 'linkify' not in parser.get_active_rules()['core']
    parser.enable('linkify')
    after = parser.render(source)
    return {'linkify_option_alone_does_not_activate_rule': inactive and '<a ' not in before,
        'existing_enable_activates_linkification': 'linkify' in parser.get_active_rules()['core']
            and '<a href="https://example.org/shop">' in after and '</a>.' in after}


def rendering() -> dict:
    """核真实token类型回调与已有属性编码。@return 渲染定制事实。"""
    parser = MarkdownIt()
    calls = []

    def decorate(renderer, tokens, index, options, env):
        """只增加已明确的属性并交还原渲染器。@param renderer 渲染器。@param tokens token序列。@param index 当前项。@param options 选项。@param env 元数据。@return HTML片段。"""
        calls.append(tokens[index].type)
        tokens[index].attrSet('target', '_blank')
        tokens[index].attrSet('rel', 'noopener noreferrer')
        tokens[index].attrSet('data-origin', 'demo" <preview>')
        return renderer.renderToken(tokens, index, options, env)

    source = '[Tea](https://example.org/orders)'
    parser.add_render_rule('business-link-style', decorate)
    wrong_name = parser.render(source)
    initially_unused = calls == [] and 'target=' not in wrong_name
    parser.add_render_rule('link_open', decorate)
    rendered = parser.render(source)
    return {'render_callback_requires_real_token_type': initially_unused and calls == ['link_open'],
        'existing_render_token_preserves_link_and_encodes_attrs': 'href="https://example.org/orders"' in rendered
            and '>Tea</a>' in rendered and 'target="_blank"' in rendered
            and 'rel="noopener noreferrer"' in rendered
            and 'data-origin="demo&quot; &lt;preview&gt;"' in rendered}


def reference_metadata() -> dict:
    """核引用首定义、重复报告与显式共享env的边界。@return 引用事实。"""
    parser = MarkdownIt()
    shared = {}
    tokens = parser.parse('[a]: https://example.org/first\n\n[a]: https://example.org/second', shared)
    first = shared['references']['A']
    duplicates = shared['duplicate_refs']
    reused = parser.render('[a]', shared)
    fresh = parser.render('[a]', {})
    return {'first_reference_and_duplicate_metadata_preserved': tokens == []
            and first['href'] == 'https://example.org/first' and first['map'] == [0, 1]
            and len(duplicates) == 1 and duplicates[0]['label'] == 'A'
            and duplicates[0]['href'] == 'https://example.org/second' and duplicates[0]['map'] == [2, 3],
        'caller_owned_reference_env_is_reused': 'href="https://example.org/first"' in reused
            and '<a ' not in fresh and '[a]' in fresh}


def main() -> None:
    """输出当前任务实际观察，始终核候选包真实位置。@return None。"""
    task = sys.argv[1]
    fields = {'IT-U01': ('block_and_inline_token_layers_are_distinct', 'source_maps_are_line_ranges'),
        'IT-C01': ('source_maps_are_line_ranges',),
        'IT-C02': ('linkify_option_alone_does_not_activate_rule', 'existing_enable_activates_linkification'),
        'IT-U02': ('render_callback_requires_real_token_type',),
        'IT-P01': ('render_callback_requires_real_token_type', 'existing_render_token_preserves_link_and_encodes_attrs'),
        'IT-U03': ('first_reference_and_duplicate_metadata_preserved',),
        'IT-C03': ('caller_owned_reference_env_is_reused',)}
    if task in ('IT-U01', 'IT-C01'):
        facts = token_maps()
    elif task == 'IT-C02':
        facts = linkification()
    elif task in ('IT-U02', 'IT-P01'):
        facts = rendering()
    else:
        facts = reference_metadata()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(markdown_it.__file__).resolve() == root / 'library/markdown_it/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
