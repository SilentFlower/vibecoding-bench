"""真实执行有限重试与等待策略；业务替身只影响本验证子进程。"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def observe(function):
    """将异常记录为独立失败。@param function 待观察断言。@return 是否满足。"""
    try:
        return bool(function())
    except Exception:
        return False


def state(attempt=1):
    """创建真实调用状态。@param attempt 业务编号。@return RetryCallState。"""
    from tenacity import RetryCallState, Retrying
    result = RetryCallState(Retrying(), None, (), {})
    result.attempt_number = attempt
    return result


def loader_case(kind='later', policy='reraise', validate=False):
    """从真实合成文件读取，记录策略与回调顺序。@param kind 文件状态。@param policy 最终异常政策。@param validate 是否校验业务字段。@return 实际记录。"""
    from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

    events, calls, sleeps, fallback_calls = [], [], [], []
    expected = {'region': '华东', 'count': 5}
    with tempfile.TemporaryDirectory(prefix='tenacity-loader-') as directory:
        path, marker = Path(directory) / 'config.json', Path(directory) / 'started.flag'
        if kind == 'ready':
            path.write_text(json.dumps(expected))
        elif kind == 'malformed':
            path.write_text('{not-json')
        elif kind == 'invalid_fields':
            path.write_text(json.dumps({'region': '华东'}))

        def before(rs):
            """在第三次调用前发布文件。@param rs 真实状态。@return None。"""
            events.append(['before', rs.attempt_number])
            if kind == 'later' and rs.attempt_number == 3:
                path.write_text(json.dumps(expected))

        def retry(rs):
            """记录并应用精确异常谓词。@param rs 真实状态。@return 是否重试。"""
            events.append(['retry', rs.attempt_number])
            return retry_if_exception_type(FileNotFoundError)(rs)

        def wait(rs):
            """记录原生等待策略求值。@param rs 状态。@return 秒数。"""
            events.append(['wait', rs.attempt_number])
            return wait_fixed(0.2)(rs)

        def stop(rs):
            """记录停止判断。@param rs 状态。@return 是否耗尽。"""
            events.append(['stop', rs.attempt_number])
            return stop_after_attempt(3)(rs)

        def sleep(seconds):
            """记录等待参数而不真实睡眠。@param seconds 等待值。@return None。"""
            sleeps.append(float(seconds))
            events.append(['sleep', float(seconds)])

        def load():
            """读取实际文件并可选校验字段。@return 真实 JSON。"""
            calls.append(1)
            events.append(['call', len(calls)])
            data = json.loads(path.read_text())
            if validate and set(data) != {'region', 'count'}:
                raise ValueError('Invalid business fields')
            return data

        def fallback(rs):
            """记录耗尽回调。@param rs 状态。@return 合成回退对象。"""
            fallback_calls.append(rs.attempt_number)
            return {'fallback': True}

        controller = Retrying(retry=retry, wait=wait, stop=stop, sleep=sleep, before=before,
            after=lambda rs: events.append(['after', rs.attempt_number]),
            before_sleep=lambda rs: events.append(['before_sleep', rs.attempt_number]),
            reraise=policy == 'reraise', retry_error_callback=fallback if policy == 'fallback' else None)
        error_type, result, final_attempt = None, None, None
        try:
            result = controller(load)
            if validate:
                marker.write_text('started')
        except Exception as error:
            error_type = type(error).__name__
            if hasattr(error, 'last_attempt'):
                final_attempt = [error.last_attempt.attempt_number, type(error.last_attempt.exception()).__name__]
        return {'calls': len(calls), 'sleeps': sleeps, 'events': events, 'result': result,
            'error_type': error_type, 'last_attempt': final_attempt, 'fallback_calls': fallback_calls,
            'marker_count': int(marker.exists())}


def lifecycle_expected(attempts, success=True, retryable=True):
    """按契约独立构造生命周期顺序。@param attempts 次数。@param success 是否最终成功。@param retryable 失败是否可重试。@return 顺序。"""
    events = []
    for attempt in range(1, attempts + 1):
        events += [['before', attempt], ['call', attempt], ['retry', attempt]]
        if attempt == attempts and (success or not retryable):
            break
        events += [['after', attempt], ['wait', attempt], ['stop', attempt]]
        if attempt < attempts:
            events += [['before_sleep', attempt], ['sleep', 0.2]]
    return events


def loader_observations(mode):
    """校验既有文件加载、异常和副作用边界。@param mode 任务。@return 独立结果。"""
    normal, ready = loader_case(), loader_case('ready')
    valid = (normal['calls'] == 3 and normal['sleeps'] == [0.2, 0.2]
        and normal['result'] == {'region': '华东', 'count': 5}
        and normal['events'] == lifecycle_expected(3)
        and ready['calls'] == 1 and ready['sleeps'] == [] and ready['events'] == lifecycle_expected(1))
    if mode == 'TN-U01':
        return {'native_lifecycle': valid}
    missing, malformed = loader_case('missing'), loader_case('malformed')
    boundaries = (missing['calls'] == 3 and missing['sleeps'] == [0.2, 0.2]
        and missing['error_type'] == 'FileNotFoundError' and malformed['calls'] == 1
        and malformed['sleeps'] == [] and malformed['error_type'] == 'JSONDecodeError')
    if mode == 'TN-C01':
        return {'native_lifecycle': valid, 'exception_boundaries': boundaries}
    if mode == 'TN-P01':
        cases = [loader_case(kind, validate=True) for kind in ('later', 'missing', 'malformed', 'invalid_fields')]
        return {'native_lifecycle': valid, 'publish_only_after_valid': [case['marker_count'] for case in cases] == [1, 0, 0, 0],
            'non_retryable_validation': cases[3]['calls'] == 1 and cases[3]['error_type'] == 'ValueError'}
    if mode == 'TN-U02':
        return {'lifecycle_sequences': valid and missing['events'] == lifecycle_expected(3, False)
            and malformed['events'] == lifecycle_expected(1, False, False)}
    wrapped, reraised, fallback = (loader_case('missing', kind) for kind in ('wrapped', 'reraise', 'fallback'))
    unrelated = loader_case('malformed', 'fallback')
    return {'final_policies': wrapped['error_type'] == 'RetryError' and wrapped['last_attempt'] == [3, 'FileNotFoundError']
        and reraised['error_type'] == 'FileNotFoundError' and fallback['result'] == {'fallback': True}
        and fallback['fallback_calls'] == [3] and unrelated['error_type'] == 'JSONDecodeError'
        and unrelated['fallback_calls'] == [] and loader_case('ready', 'fallback')['fallback_calls'] == []}


def reentrant_observations():
    """用事件和真实状态区分共享统计串扰。@return 原版可复现事实。"""
    from tenacity import retry, stop_after_attempt, wait_none
    seen, attempts = [], {0: 0, 1: 0}

    def before(rs):
        """记录真实调用身份和共享表。@param rs 状态。@return None。"""
        seen.append([rs.args[0], rs.attempt_number, rs.retry_object.statistics['attempt_number']])

    @retry(stop=stop_after_attempt(3), wait=wait_none(), sleep=lambda seconds: None, reraise=True, before=before)
    def nested(depth):
        """有限重入：内层三次，外层两次。@param depth 深度。@return 成功。"""
        attempts[depth] += 1
        if depth == 0 and attempts[0] < 3:
            raise ValueError('inner transient')
        if depth == 1 and attempts[1] == 1:
            nested(0)
            raise ValueError('outer transient')
        return 'ok'

    result = nested(1)
    return {'result': result, 'attempts': [attempts[0], attempts[1]], 'events': seen,
        'ordinary_control': loader_case()['calls'] == 3}


def stop_observations():
    """使用真实 outcome 时间字段而不改平台时钟。@return 停止边界。"""
    from tenacity import Retrying, stop_after_delay, stop_before_delay
    rs = state()
    rs.set_result(None)
    rs.outcome_timestamp = rs.start_time + 2
    values = []
    for upcoming in (4, 3, 2):
        rs.upcoming_sleep = upcoming
        values.append([stop_after_delay(5)(rs), stop_before_delay(5)(rs)])
    stops = []
    result = Retrying(stop=lambda current: stops.append(1) or True, sleep=lambda seconds: None)(lambda: 'completed')
    return {'boundaries': values, 'successful_call_not_retroactively_stopped': result == 'completed' and not stops}


async def async_observations():
    """原生异步读取及取消只在本子进程内运行。@return 真实结果。"""
    from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed
    with tempfile.TemporaryDirectory(prefix='tenacity-async-') as directory:
        path = Path(directory) / 'config.json'
        attempts, sleeps, yielded = [], [], []

        def before(rs):
            """发布实际合成文件。@param rs 状态。@return None。"""
            if rs.attempt_number == 3:
                path.write_text('{"ready":true}')

        async def sleep(seconds):
            """真实 await 让出事件循环但不等待业务秒数。@param seconds 请求秒数。@return None。"""
            sleeps.append(float(seconds))
            await asyncio.sleep(0)
            yielded.append(True)

        async def load():
            """读取真实合成文件。@return JSON。"""
            attempts.append(1)
            return json.loads(path.read_text())

        controller = AsyncRetrying(retry=retry_if_exception_type(FileNotFoundError), stop=stop_after_attempt(3),
            wait=wait_fixed(0.2), sleep=sleep, before=before, reraise=True)
        result = await asyncio.wait_for(controller(load), timeout=2)
        entered, blocker, cancelled_calls = asyncio.Event(), asyncio.Event(), []

        async def blocked_sleep(seconds):
            """等待取消证明，不使用真实长睡眠。@param seconds 请求值。@return None。"""
            entered.set()
            await blocker.wait()

        async def missing():
            """制造暂态缺文件。@return 不返回。"""
            cancelled_calls.append(1)
            raise FileNotFoundError('synthetic')

        task = asyncio.create_task(AsyncRetrying(retry=retry_if_exception_type(FileNotFoundError),
            stop=stop_after_attempt(3), wait=wait_fixed(0.2), sleep=blocked_sleep, reraise=True)(missing))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True
        else:
            cancelled = False
        exhausted_calls = []

        async def permanently_missing():
            """记录有限耗尽。@return 不返回。"""
            exhausted_calls.append(1)
            raise FileNotFoundError('synthetic')

        async def no_sleep(seconds):
            """保留 await 协议。@param seconds 请求值。@return None。"""
            await asyncio.sleep(0)

        try:
            await AsyncRetrying(retry=retry_if_exception_type(FileNotFoundError), stop=stop_after_attempt(3),
                sleep=no_sleep, reraise=True)(permanently_missing)
        except FileNotFoundError:
            exhausted = len(exhausted_calls) == 3
        else:
            exhausted = False
        return {'async_native_read': result == {'ready': True} and len(attempts) == 3 and sleeps == [0.2, 0.2] and len(yielded) == 2,
            'cancellation_propagates': cancelled and len(cancelled_calls) == 1, 'bounded_exhaustion': exhausted}


def zero_observations():
    """独立核零贡献、clamp、随机采样与正倍率兼容。@return 业务断言。"""
    from tenacity import Retrying, stop_after_attempt, wait_exponential, wait_exponential_jitter, wait_random_exponential
    from tenacity import wait as wait_module
    matrix, bounds, draws = [], [], []

    def uniform(low, high):
        """由实际边界生成确定采样。@param low 下界。@param high 上界。@return 四分位值。"""
        draws.append([low, high])
        return low + (high - low) / 4

    with patch.object(wait_module.random, 'uniform', uniform):
        for multiplier in (0, 0.0):
            for base in (2, 2.0):
                for attempt in (1, 1024, 1025, 2049):
                    for minimum in (0, 3):
                        rs = state(attempt)
                        fixed = wait_exponential(multiplier=multiplier, exp_base=base, min=minimum, max=60)(rs)
                        before = len(draws)
                        random = wait_random_exponential(multiplier=multiplier, exp_base=base, min=minimum, max=60)(rs)
                        bounds.append(fixed == minimum and random == minimum and draws[-1] == [minimum, minimum] and len(draws) == before + 1)
                        for maximum, jitter in ((60, 0), (60, 1), (0.1, 1)):
                            before = len(draws)
                            actual = wait_exponential_jitter(multiplier=multiplier, exp_base=base, min=minimum, max=maximum, jitter=jitter)(rs)
                            expected = max(max(0, minimum), min(jitter / 4, maximum))
                            matrix.append(actual == expected and draws[-1] == [0, jitter] and len(draws) == before + 1)
        positive = all(wait_exponential(multiplier=m, exp_base=b, min=3, max=60)(state(a)) == max(3, min(m * b ** (a - 1), 60))
            for m in (1, 2.5) for b in (2, 2.0) for a in (1, 2, 5, 20))
    events = []

    class ExplodingPower(float):
        """确保零贡献和既有正倍率封顶不计算无关幂。"""
        def __pow__(self, exponent):
            """暴露被错误求值的幂。@param exponent 指数。@return 不返回。"""
            raise AssertionError('irrelevant exponent evaluated')

    class RecordingPower(float):
        """记录既有 jitter 先采样后求幂的顺序。"""
        def __pow__(self, exponent):
            """返回真实幂并记录。@param exponent 指数。@return 浮点幂。"""
            events.append('power')
            return float(self) ** exponent

    def record_uniform(low, high):
        """记录随机顺序。@param low 下界。@param high 上界。@return 四分位。"""
        events.append('draw')
        return low + (high - low) / 4

    early = wait_exponential(multiplier=1, exp_base=ExplodingPower(2), max=60)(state(2049)) == 60
    zero_skips = observe(lambda: wait_exponential(multiplier=0.0, exp_base=ExplodingPower(2), max=60)(state(2049)) == 0)
    with patch.object(wait_module.random, 'uniform', record_uniform):
        jitter_zero = observe(lambda: wait_exponential_jitter(multiplier=0, exp_base=ExplodingPower(2), max=60, jitter=1)(state(2049)) == 0.25)
        events.clear()
        positive_jitter = wait_exponential_jitter(multiplier=2, exp_base=RecordingPower(2), max=60, jitter=1)(state(2))
        order = positive_jitter == 4.25 and events == ['draw', 'power']
    calls, sleeps = [], []

    def operation():
        """真实控制器执行有限业务。@return 成功值。"""
        calls.append(1)
        if len(calls) < 3:
            raise ValueError('transient')
        return 'done'

    result = Retrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.0, max=60),
        sleep=lambda seconds: sleeps.append(float(seconds)), reraise=True)(operation)
    return {'zero_clamp_jitter_matrix': all(matrix), 'random_exponential_bounds': all(bounds),
        'positive_compatibility': positive and early and order, 'irrelevant_power_skipped': zero_skips and jitter_zero,
        'real_controller': result == 'done' and len(calls) == 3 and sleeps == [0.0, 0.0]}


def zero_diagnosis():
    """原版缺陷事实单独归属诊断，不要求其他任务先修。@return 真实原版观察。"""
    from tenacity import wait_exponential, wait_exponential_jitter, wait_random_exponential
    from tenacity import wait as wait_module
    rs = state(1025)
    calls = []

    def uniform(low, high):
        """保留边界意义。@param low 下界。@param high 上界。@return 四分位。"""
        calls.append([low, high])
        return low + (high - low) / 4

    with patch.object(wait_module.random, 'uniform', uniform):
        return {'float_zero': wait_exponential(multiplier=0.0, max=60)(rs),
            'float_base_zero': wait_exponential(multiplier=0, exp_base=2.0, max=60)(rs),
            'integer_control': wait_exponential(multiplier=0, exp_base=2, max=60)(rs),
            'random': wait_random_exponential(multiplier=0.0, max=60)(rs),
            'jitter': wait_exponential_jitter(multiplier=0.0, max=60, jitter=1)(rs), 'draws': calls}


def combination_observations():
    """独立核深树分组、顺序、动态子节点及有界环错误。@return 断言结果。"""
    from tenacity import wait_combine, wait_fixed
    rs, recursion_limit = state(), sys.getrecursionlimit()

    def deep():
        """构造左右与混合深树，独立预期为叶数。@return 是否正常。"""
        for depth in (1000, 2000):
            left = right = mixed = wait_fixed(1)
            for index in range(depth):
                left = wait_combine(left, wait_fixed(1))
                right = wait_combine(wait_fixed(1), right)
                mixed = wait_combine(mixed, wait_fixed(1)) if index % 2 else wait_combine(wait_fixed(1), mixed)
            if any(tree(rs) != float(depth + 1) for tree in (left, right, mixed)):
                return False
        return sys.getrecursionlimit() == recursion_limit

    def grouping():
        """保护原树分组及非有限浅树数学行为。@return 是否保持。"""
        grouped = wait_combine(wait_combine(wait_fixed(1e16), wait_fixed(1)), wait_fixed(-1e16))
        if grouped(rs) != 0.0 or wait_combine(wait_fixed(1e16), wait_fixed(1), wait_fixed(-1e16))(rs) != 1.0:
            return False
        for values in ((float('inf'), 1.0), (float('nan'), 2.0), (float('inf'), -float('inf'))):
            expected = float(sum(values))
            actual = wait_combine(*(lambda current, value=value: value for value in values))(rs)
            if not (math.isnan(expected) and math.isnan(actual)) and actual != expected:
                return False
        return wait_combine()(rs) == 0.0

    def opaque_order_and_dag():
        """子类不透明，合法 DAG 每次出现均求值。@return 是否保持。"""
        events = []

        class Opaque(wait_combine):
            """带自定义求值的组合必须按 callable 调用。"""
            def __call__(self, current):
                """保留额外业务值。@param current 状态。@return 求和值加七。"""
                events.append('opaque')
                return float(sum(child(current) for child in self.wait_funcs)) + 7

        class Falsy:
            """合法但布尔值为假的 callable。"""
            def __bool__(self):
                """返回假值。@return False。"""
                return False
            def __call__(self, current, /):
                """仅接受位置参数。@param current 状态。@return 二。"""
                events.append('falsy')
                return 2

        custom = wait_combine(Opaque(wait_fixed(1), wait_fixed(2)), wait_fixed(4))(rs)
        if custom != 14 or events != ['opaque']:
            return False
        events.clear()

        def leaf(current, /):
            """记录共享子树每次实际调用。@param current 状态。@return 一。"""
            events.append('leaf')
            return 1

        shared = wait_combine(leaf, Falsy())
        value = wait_combine(shared, shared, lambda current: 4)(rs)
        return value == 10 and events == ['leaf', 'falsy', 'leaf', 'falsy']

    def dynamic():
        """未进入节点读新属性，已进入节点保留原迭代器。@return 是否保持。"""
        later = wait_combine(wait_fixed(2))
        root = wait_combine()

        def change(current):
            """修改随后进入的节点及已进入根属性。@param current 状态。@return 一。"""
            later.wait_funcs = (wait_fixed(7),)
            root.wait_funcs = (wait_fixed(99),)
            return 1

        root.wait_funcs = (change, later)
        if root(rs) != 8:
            return False
        node = wait_combine()

        def rebind(current):
            """当前 tuple 迭代不跟随属性重绑。@param current 状态。@return 一。"""
            node.wait_funcs = (wait_fixed(100),)
            return 1

        node.wait_funcs = (rebind, wait_fixed(2))
        return node(rs) == 3

    def exceptions():
        """叶失败不得继续调用后叶；循环需明确 ValueError。@return 是否符合。"""
        events = []

        def failing(current):
            """模拟业务叶异常。@param current 状态。@return 不返回。"""
            events.append('failure')
            raise LookupError('leaf')

        try:
            wait_combine(failing, lambda current: events.append('later') or 2)(rs)
        except LookupError:
            pass
        else:
            return False
        if events != ['failure']:
            return False
        first, second = wait_combine(), wait_combine()
        first.wait_funcs = (first,)
        for root in (first, second):
            if root is second:
                first.wait_funcs, second.wait_funcs = (second,), (first,)
            try:
                root(rs)
            except ValueError as error:
                if not str(error).strip():
                    return False
            except Exception:
                return False
            else:
                return False
        return True

    return {'deep_trees': observe(deep), 'grouping_and_numbers': observe(grouping),
        'opaque_order_and_dag': observe(opaque_order_and_dag), 'dynamic_entry': observe(dynamic),
        'exceptions_and_cycles': observe(exceptions), 'recursion_limit_unchanged': sys.getrecursionlimit() == recursion_limit}


def combination_diagnosis():
    """捕获原版深树错误，同时保留浅树正常对照。@return 诊断事实。"""
    from tenacity import wait_combine, wait_fixed
    rs = state()
    items = [wait_fixed(1) for _ in range(1000)]
    try:
        sum(items)(rs)
    except RecursionError:
        deep_error = 'RecursionError'
    else:
        deep_error = None
    events = []

    class Custom(wait_combine):
        """浅层自定义求值对照。"""
        def __call__(self, current):
            """保持扩展值与逐叶调用。@param current 状态。@return 求和加七。"""
            return float(sum(child(current) for child in self.wait_funcs)) + 7

    def leaf(value):
        """生成带可见事件的叶策略。@param value 常量。@return callable。"""
        def call(current):
            """记录一次真实调用。@param current 状态。@return 常量。"""
            events.append(value)
            return value
        return call

    custom_value = wait_combine(Custom(leaf(1), leaf(2)), leaf(4))(rs)
    return {'deep_error': deep_error, 'flat': wait_combine(*items)(rs),
        'grouped': (wait_fixed(1e16) + wait_fixed(1) + wait_fixed(-1e16))(rs),
        'flat_float': wait_combine(wait_fixed(1e16), wait_fixed(1), wait_fixed(-1e16))(rs),
        'custom_value': custom_value, 'leaf_order': events}


def main():
    """执行固定业务模式并输出单个 JSON。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode')
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    args = parser.parse_args()
    root = args.candidate_root.resolve()
    sys.path.insert(0, str(root / 'library'))
    import tenacity
    imported = Path(tenacity.__file__).resolve().is_relative_to(root / 'library')
    if args.mode in ('TN-U01', 'TN-C01', 'TN-P01', 'TN-C02', 'TN-U02'):
        result = loader_observations(args.mode)
    elif args.mode == 'TN-D02':
        result = reentrant_observations()
    elif args.mode == 'TN-C03':
        result = stop_observations()
    elif args.mode == 'TN-P02':
        result = asyncio.run(async_observations())
    elif args.mode == 'TN-D03':
        result = zero_diagnosis()
    elif args.mode == 'TN-M01':
        result = zero_observations()
    elif args.mode == 'TN-D04':
        result = combination_diagnosis()
    elif args.mode == 'TN-M02':
        result = combination_observations()
    else:
        raise ValueError(args.mode)
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
