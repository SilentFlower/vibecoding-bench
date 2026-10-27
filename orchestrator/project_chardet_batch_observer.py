"""按公开行为验收批量编码检测，兼容未约定的编号起点与错误表示。"""
import json
import os
from pathlib import Path

import chardet


def _failed(row) -> bool:
    """判断失败记录是否保留可辨认的错误事实。:param row: 候选记录。:return: 是否明确失败。"""
    if not isinstance(row, dict) or 'result' not in row or row['result'] is not None:
        return False
    error = row.get('error')
    if isinstance(error, Exception):
        return True
    if isinstance(error, str):
        return bool(error.strip())
    # 合同没有规定错误字段名；保留类型、消息或原因等事实的结构化表示均可接受。
    return isinstance(error, dict) and any(isinstance(value, str) and value.strip() for value in error.values())


def _results(detect_many) -> bool:
    """比较真实检测结果及重复标识，不固定内部实现。:param detect_many: 候选接口。:return: 结果是否保持。"""
    records = [('same', b'plain'), ('same', bytearray(b'\xef\xbb\xbftext')), (None, b''), (['id'], b'caf\xe9')]
    for rename in (False, True):
        rows = list(detect_many(records, should_rename_legacy=rename))
        if len(rows) != len(records):
            return False
        for row, (identifier, payload) in zip(rows, records):
            if (not isinstance(row, dict) or not {'index', 'id', 'result', 'error'} <= row.keys()
                    or row.get('id') != identifier or row.get('error') is not None
                    or row.get('result') != chardet.detect(payload, should_rename_legacy=rename)):
                return False
    return True


def _order(detect_many) -> bool:
    """只要求编号连续且保留顺序，允许从零或一开始。:param detect_many: 候选接口。:return: 顺序是否正确。"""
    rows = list(detect_many([('same', b'a'), ('same', b'b'), ('last', b'c')]))
    indexes = [row.get('index') for row in rows]
    return (len(rows) == 3 and [row.get('id') for row in rows] == ['same', 'same', 'last']
        and all(type(index) is int for index in indexes) and indexes in ([0, 1, 2], [1, 2, 3]))


def _laziness(detect_many) -> bool:
    """检查创建、逐条消费及关闭时均不提前读取后续输入。:param detect_many: 候选接口。:return: 是否惰性。"""
    seen = []

    def records():
        """记录输入被实际消费的时刻。:return: 记录迭代器。"""
        for index in range(3):
            seen.append(index)
            yield index, b'plain'

    stream = detect_many(records())
    if seen or next(stream)['id'] != 0 or seen != [0]:
        return False
    stream.close()
    return seen == [0]


def _errors(detect_many) -> bool:
    """局部失败不得产生成功结果或阻断后续合法记录。:param detect_many: 候选接口。:return: 是否隔离错误。"""
    rows = list(detect_many([('bad', 'text'), ('bad-shape',), ('after', b'plain')]))
    return (len(rows) == 3 and rows[0].get('id') == 'bad' and _failed(rows[0]) and _failed(rows[1])
        and rows[2].get('id') == 'after' and rows[2].get('error') is None
        and rows[2].get('result') == chardet.detect(b'plain'))


def _policies(detect_many) -> bool:
    """检查停止和抛错策略均不消费后续记录。:param detect_many: 候选接口。:return: 策略是否有效。"""
    for policy in ('stop', 'raise'):
        source = iter([('first', b'plain'), ('bad', 3), ('tail', b'end')])
        stream = detect_many(source, on_error=policy)
        if next(stream)['id'] != 'first':
            return False
        if policy == 'stop':
            remaining = list(stream)
            if len(remaining) != 1 or not _failed(remaining[0]):
                return False
        else:
            try:
                next(stream)
            except TypeError:
                pass
            else:
                return False
        if next(source)[0] != 'tail':
            return False
    return True


def _upstream(detect_many) -> bool:
    """上游迭代异常必须原样传播，不能伪装成局部记录错误。:param detect_many: 候选接口。:return: 是否传播。"""
    for policy in ('continue', 'stop', 'raise'):
        failure = LookupError('upstream')

        def records():
            """产生正常记录后抛出上游异常。:return: 输入迭代器。"""
            yield 'first', b'plain'
            raise failure

        stream = detect_many(records(), on_error=policy)
        if next(stream)['id'] != 'first':
            return False
        try:
            next(stream)
        except LookupError as error:
            if error is not failure:
                return False
        else:
            return False
    return True


def _detection(detect_many) -> bool:
    """检查真实逐条检测及整份字节输入拒绝。:param detect_many: 候选接口。:return: 是否符合检测边界。"""
    for raw in (b'not records', bytearray(b'not records')):
        try:
            list(detect_many(raw))
        except TypeError:
            pass
        else:
            return False
    detector = chardet.UniversalDetector
    created = []

    def fresh_detector(*args, **kwargs):
        """观察真实 detect 内部的独立检测器创建。:param args: 原参数。:param kwargs: 原选项。:return: 原检测器。"""
        created.append(True)
        return detector(*args, **kwargs)

    # 在真实 detect 的内部依赖处观察，允许候选提前导入或别名引用 detect。
    chardet.UniversalDetector = fresh_detector
    try:
        rows = list(detect_many([('same', b'plain')] * 3))
    finally:
        chardet.UniversalDetector = detector
    return len(rows) == 3 and len(created) == 3


def main() -> None:
    """执行独立业务矩阵并只输出受信反馈类别。:return: None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    checks = dict.fromkeys(('batch_api', 'batch_results', 'batch_order', 'batch_laziness',
        'batch_errors', 'batch_policies', 'batch_upstream', 'batch_detection'), False)
    try:
        from chardet.batch import detect_many
        checks['batch_api'] = callable(detect_many)
    except ImportError:
        detect_many = None
    if checks['batch_api']:
        for code, check in (('batch_results', _results), ('batch_order', _order),
                ('batch_laziness', _laziness), ('batch_errors', _errors), ('batch_policies', _policies),
                ('batch_upstream', _upstream), ('batch_detection', _detection)):
            try:
                checks[code] = bool(check(detect_many))
            except Exception:
                # 一项失败不遮住其他已核对事实；异常正文留在隔离执行中，不进入模型反馈。
                pass
    print(json.dumps({'candidate_import': Path(chardet.__file__).resolve().is_relative_to(root / 'library'),
        'business': all(checks.values()), 'feedback_codes': [code for code, passed in checks.items() if not passed]}))


if __name__ == '__main__':
    main()
