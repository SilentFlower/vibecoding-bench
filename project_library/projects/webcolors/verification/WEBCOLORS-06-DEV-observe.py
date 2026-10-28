"""通过公开 Mapping 行为验证色板，不限定私有存储字段。"""
import json
import os
from pathlib import Path
import sys


def main() -> None:
    """检查真实候选的值、不可变性及输入输出隔离。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    sys.path.insert(0, str(root / 'library/src'))
    import webcolors
    checks = dict.fromkeys(('palette_values', 'palette_isolation', 'palette_immutable', 'palette_builtins'), False)
    try:
        from webcolors.palette import Palette
        source = {'Primary': '#123', 'other': '#112233'}
        first, second = Palette(source), Palette({'primary': '#abc'})
        checks['palette_values'] = (first['PRIMARY'] == '#112233' and second['PRIMARY'] == '#aabbcc'
            and first.rgb('primary') == webcolors.hex_to_rgb('#112233')
            and first.aliases('#123') == ('other', 'primary') and tuple(first) == ('other', 'primary'))
        # 不可变性指公开行为及所有权；内部字段可以有不同名称或表示。
        source['Primary'] = '#000'
        exported = first.to_dict()
        exported['primary'] = '#000'
        checks['palette_isolation'] = first['primary'] == '#112233' and second['primary'] == '#aabbcc'
        try:
            first['primary'] = '#000'
        except TypeError:
            checks['palette_immutable'] = first['primary'] == '#112233'
        checks['palette_builtins'] = all(
            len(palette) == len(webcolors.names(specification)) + 1
            and all(palette[name] == webcolors.name_to_hex(name, specification) for name in webcolors.names(specification))
            for specification in ('html4', 'css2', 'css21', 'css3')
            for palette in (Palette({'brand-color': '#123'}, base_spec=specification),))
    except Exception:
        # 开发错误只能产生失败，不能充当合理参数拒绝。
        pass
    codes = [name for name, passed in checks.items() if not passed]
    print(json.dumps({'candidate_import': Path(webcolors.__file__).resolve().is_relative_to(root / 'library'),
        'business': not codes, 'feedback_codes': codes}))


if __name__ == '__main__':
    main()
