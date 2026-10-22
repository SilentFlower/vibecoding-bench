"""核颜色规范、严格格式、截断归一化和历史兼容解析。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import webcolors


def main() -> None:
    """读取实际候选输出，区分格式转换与业务输入校验。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(webcolors.__file__).resolve() == root / 'library/src/webcolors/__init__.py'}
    task = argv[1]
    if task == 'WC-U01':
        rejected = False
        try:
            webcolors.name_to_hex('orange', spec='html4')
        except ValueError:
            rejected = True
        result['named_color_membership_depends_on_the_explicit_specification'] = (
            rejected and webcolors.name_to_hex('orange', spec='css21') == '#ffa500'
            and webcolors.name_to_hex('GRAY', spec='css3') == '#808080')
    elif task == 'WC-U02':
        rejected = False
        try:
            webcolors.html5_parse_simple_color('#abc')
        except ValueError:
            rejected = True
        result['hex_normalization_and_html5_simple_validation_have_distinct_input_contracts'] = (
            webcolors.normalize_hex('#AbC') == '#aabbcc' and rejected
            and tuple(webcolors.html5_parse_simple_color('#aabbcc')) == (170, 187, 204))
    elif task == 'WC-C01':
        result['integer_rgb_normalization_clips_invalid_channels_instead_of_rejecting'] = (
            tuple(webcolors.normalize_integer_triplet((300, -5, 128))) == (255, 0, 128)
            and webcolors.rgb_to_hex((300, -5, 128)) == '#ff0080')
    elif task == 'WC-C02':
        rejected = False
        try:
            webcolors.html5_parse_simple_color('chucknorris')
        except ValueError:
            rejected = True
        result['legacy_browser_color_recovery_is_not_strict_color_validation'] = (
            tuple(webcolors.html5_parse_legacy_color('chucknorris')) == (192, 0, 0) and rejected)
    elif task == 'WC-P01':
        rgb = webcolors.rgb_percent_to_rgb(('30%', '50%', '70%'))
        result['percentage_conversion_quantizes_and_named_reverse_lookup_loses_alias_spelling'] = (
            tuple(rgb) == (76, 128, 178)
            and tuple(webcolors.rgb_to_rgb_percent(rgb)) == ('29.80%', '50%', '69.80%')
            and webcolors.name_to_hex('aqua') == webcolors.name_to_hex('cyan') == '#00ffff'
            and webcolors.hex_to_name('#00ffff') == 'cyan')
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
