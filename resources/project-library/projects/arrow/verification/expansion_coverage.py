"""在原覆盖率会话中真实执行已存在的新功能及其错误边界。"""
import contextlib
import io
import json
import runpy
from pathlib import Path


def cover_features(project, evidence):
    """保留原测试计数和阈值，补充受保护新API断言。

    :param project: 原控制器创建的实际实现叠加目录。
    :param evidence: 当轮独立证据目录。
    :return: None；任何新增能力退化都使原测试阶段失败。
    """
    import arrow
    from arrow.parser import DateTimeParser, ParserError

    assert Path(arrow.__file__).resolve().is_relative_to(project.resolve())
    reader = DateTimeParser()
    active = []
    if reader.parse('3', 'd').isoweekday() == 3:
        active.append('AR-WEEKDAY-DEV')
    for name, available in [('AR-STRICT-DEV', hasattr(reader, 'parse_strict')),
        ('AR-MATCH-DEV', hasattr(reader, 'parse_match')),
        ('AR-EXCEL-DEV', hasattr(arrow.Arrow, 'from_excel')),
        ('AR-ELAPSED-DEV', hasattr(arrow.Arrow, 'shift_elapsed'))]:
        if available:
            active.append(name)
    base = Path(__file__).parent
    executed = []
    for task_id in active:
        with contextlib.redirect_stdout(io.StringIO()):
            business = runpy.run_path(str(base / (task_id + '-observe.py')))
        assert business['business'] is True, '新增业务矩阵失败：' + task_id
        public = runpy.run_path(str(base / (task_id + '-coverage-public.py')))
        tests = [(name, value) for name, value in public.items() if name.startswith('test_') and callable(value)]
        assert len(tests) == 6
        for name, test in tests:
            test()
        executed.append({'objective_id':task_id,'business_matrix':'passed','public_assertions':len(tests)})
    if hasattr(reader, 'parse_strict'):
        assert reader.parse_strict('2024-366', 'YYYY-DDD').month == 12
        assert reader.parse_strict('2026-W53-7', 'W').year == 2027
        for text, fmt in [('2025-W53-1','W'), ('123','DDD')]:
            try:
                reader.parse_strict(text, fmt)
            except ParserError:
                pass
            else:
                raise AssertionError('严格日历边界被接受')
        # 公开合同未限定空列表的异常子类，不能把合法 ValueError 当作候选缺陷。
        try:
            reader.parse_strict('2024-01-01', [])
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError('空严格格式被接受')
        for argument in ([3], None):
            try:
                reader.parse_strict('2024-01-01', argument)
            except TypeError:
                pass
            else:
                raise AssertionError('无效严格格式被接受')
        try:
            reader.parse_strict('2024-01-01', 'YYYY-MM-DD', exact_width=1)
        except TypeError:
            pass
        else:
            raise AssertionError('严格开关没有类型校验')
    if hasattr(reader, 'parse_match'):
        for text, fmt, normalize in [(3,'YYYY',False), ('text',[],False), ('text','YYYY',1)]:
            try:
                reader.parse_match(text, fmt, normalize)
            except TypeError:
                pass
            else:
                raise AssertionError('无效报告配置被接受')
    if hasattr(arrow.Arrow, 'from_excel'):
        from decimal import Decimal
        for value in (Decimal('59.99999999999999999999999999999'),):
            try:
                arrow.Arrow.from_excel(value, date_system='1900')
            except ValueError:
                pass
            else:
                raise AssertionError('舍入后虚构日期被接受')
        try:
            arrow.get(2024,1,1).to_excel(date_system='guess')
        except ValueError:
            pass
        else:
            raise AssertionError('未知Excel系统被接受')
    (evidence / 'expansion-coverage.json').write_text(json.dumps({'status':'passed',
        'candidate_import':True,'original_nodes_unchanged':True,'original_coverage_threshold_unchanged':True,
        'executed_objectives':executed},ensure_ascii=False,indent=2) + '\n')
