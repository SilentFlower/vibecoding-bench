"""按公开合同核对语言偏好，容忍未约定的冲突解释并输出固定反馈类别。"""
import json
import os
from pathlib import Path

import babel
from babel.core import negotiate_locale


def _invalid_headers(negotiate) -> bool:
    """验证公开的参数拒绝和输入上限。:param negotiate: 候选协商函数。:return: 是否拒绝非法头部。"""
    for header in ('en;q=1.1', 'en;q=0.1234', 'en;bad=1', 'en,' * 100, 'en' + ' ' * 8191):
        try:
            negotiate(header, ['en'])
        except (TypeError, ValueError):
            continue
        return False
    return negotiate('', ['en']) is None


def _available_once(negotiate) -> bool:
    """使用一次性数据核对完整物化。:param negotiate: 候选协商函数。:return: 是否只消费一次可用区域。"""
    consumed = []

    def available():
        """逐项记录真实消费，避免可重复列表掩盖错误。:return: 可用区域迭代器。"""
        for locale in ('de', 'fr'):
            consumed.append(locale)
            yield locale

    return negotiate('fr, de', available()) == 'fr' and consumed == ['de', 'fr']


def _exclusions(negotiate) -> bool:
    """核对明确排除，保留合同未确定的显式冲突解释。:param negotiate: 候选协商函数。:return: 是否符合公开排除规则。"""
    if (negotiate('en-US;q=0, *', ['en_US', 'de_DE']) != 'de_DE'
            or negotiate('en;q=0, *;q=0.5', ['en_US', 'fr']) != 'fr'
            or negotiate('*;q=0', ['fr']) is not None):
        return False
    # 公开合同只明确通配符排除，不强制广泛排除与更具体正权重偏好冲突时的唯一解释。
    return negotiate('en;q=0, en-US;q=1, fr;q=0.1', ['en_US', 'fr']) in ('en_US', 'fr')


def main() -> None:
    """独立执行公开行为矩阵，失败只发布受信类别。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    checks = dict.fromkeys(('locale_preferences_api', 'locale_preferences_quality',
        'locale_preferences_order', 'locale_preferences_matching', 'locale_preferences_exclusions',
        'locale_preferences_headers', 'locale_preferences_once', 'locale_preferences_legacy'), False)
    try:
        from babel.core import negotiate_locale_preferences
        checks['locale_preferences_api'] = callable(negotiate_locale_preferences)
    except ImportError:
        negotiate_locale_preferences = None
    if checks['locale_preferences_api']:
        negotiate = negotiate_locale_preferences
        cases = (
            ('locale_preferences_quality', lambda: (
                negotiate('zh-TW;q=0.7,en;q=0.8', ['zh_TW', 'en_US']) == 'en_US'
                and negotiate('en-US;q=0.5, de-DE;q=0.9', ['en_US', 'de_DE']) == 'de_DE')),
            ('locale_preferences_order', lambda: negotiate('fr-CA;q=0.8,de;q=0.8', ['de', 'fr']) == 'fr'),
            ('locale_preferences_matching', lambda: (
                negotiate('de-de', ['de_de']) == 'de_de' and negotiate('no', ['nb_NO']) == 'nb_NO'
                and negotiate('de-DE', ['de-DE'], sep='-') == 'de-DE')),
            ('locale_preferences_exclusions', lambda: _exclusions(negotiate)),
            ('locale_preferences_headers', lambda: _invalid_headers(negotiate)),
            ('locale_preferences_once', lambda: _available_once(negotiate)),
            ('locale_preferences_legacy', lambda: negotiate_locale(['de_DE'], ['de']) == 'de'),
        )
        for code, check in cases:
            try:
                checks[code] = bool(check())
            except Exception:
                pass
    print(json.dumps({'candidate_import': Path(babel.__file__).resolve().is_relative_to(root / 'library'),
        'business': all(checks.values()), 'feedback_codes': [code for code, passed in checks.items() if not passed]}))


if __name__ == '__main__':
    main()
