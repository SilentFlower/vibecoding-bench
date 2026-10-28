"""核对书目校验的实际诊断和版本拒绝，不追加未公开的异常子类限制。"""
import json
import os
from pathlib import Path
import sys


def main() -> None:
    """执行正常诊断、无副作用与非法版本拒绝检查。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    sys.path.insert(0, str(root / 'library'))
    import bibtexparser
    checks = dict.fromkeys(('bibliography_diagnostics', 'bibliography_immutable', 'bibliography_version'), False)
    try:
        from bibtexparser.validation import validate_entries
        from bibtexparser.model import Entry, Field
        source = bibtexparser.Library([Entry('unknown', 'a', []), Entry('article', 'b', [Field('title', '  ')])])
        rows = validate_entries(source)
        checks['bibliography_diagnostics'] = (rows[0]['code'] == 'unknown-type'
            and any(row['key'] == 'b' and row['field'] == 'title' for row in rows)
            and validate_entries(bibtexparser.Library()) == ())
        checks['bibliography_immutable'] = source.entries[1]['title'] == '  ' and len(source.entries) == 2
        try:
            validate_entries(source, version='future')
        except (ValueError, TypeError, LookupError):
            # 公开合同要求明确拒绝未知版本，没有指定一个唯一异常子类。
            checks['bibliography_version'] = source.entries[1]['title'] == '  ' and len(source.entries) == 2
    except Exception:
        pass
    codes = [name for name, passed in checks.items() if not passed]
    print(json.dumps({'candidate_import': Path(bibtexparser.__file__).resolve().is_relative_to(root / 'library'),
        'business': not codes, 'feedback_codes': codes}))


if __name__ == '__main__':
    main()
